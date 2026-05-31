from __future__ import annotations

import math
import hashlib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from statistics import mean, median
from typing import Any

from contract_radar.backtest import looks_like_false_positive
from contract_radar.history import _profile_award_fit, meaningful_terms
from contract_radar.matcher import evaluate_opportunities
from contract_radar.models import (
    AwardRecord,
    BidRecommendation,
    BusinessProfile,
    EvaluatedOpportunity,
    MarketFitSignal,
    ModelExplanation,
    Solicitation,
)


ACTIONABLE_TRAINING_LABELS = {"Pursue", "Review"}
FEATURE_NAMES = [
    "matched_term_count",
    "skill_match_ratio",
    "good_fit_overlap",
    "bad_fit_overlap",
    "top_division_match",
    "profile_category_overlap",
    "missing_requirement_count",
    "rejection_reason_count",
    "trace_hard_blocker_count",
    "trace_soft_warning_count",
    "trace_positive_signal_count",
    "historical_similar_log",
    "historical_award_median_ratio",
    "historical_accessible",
    "deadline_manageable",
    "deadline_tight",
    "deadline_critical",
    "deadline_unknown",
    "days_until_deadline_clipped",
    "type_rfq_or_quotation",
    "type_tender",
    "type_rfp",
    "type_rfsq",
    "pursuit_load_clear",
    "pursuit_load_busy",
    "pursuit_load_overloaded",
    "response_enough_time",
    "response_tight",
    "response_at_risk",
    "execution_fits_team",
    "execution_needs_review",
    "execution_likely_too_large",
    "recommended_pursue_now",
    "recommended_pursue_after_review",
    "recommended_monitor",
    "recommended_skip",
    "nemotron_blocker_count",
    "requirement_document_count",
]
MARKET_FEATURE_NAMES = [
    "profile_term_overlap",
    "skill_match_ratio",
    "good_fit_overlap",
    "bad_fit_overlap",
    "missing_capability_overlap",
    "top_division_match",
    "category_construction",
    "category_professional",
    "category_goods",
    "type_rfq_or_quotation",
    "type_tender",
    "type_rfp",
    "type_rfsq",
    "award_value_log",
    "award_value_to_capacity",
    "award_under_capacity",
    "award_partner_band",
    "award_too_large",
    "prior_segment_awards_log",
    "prior_segment_supplier_log",
    "prior_top_supplier_share",
    "prior_segment_median_value_ratio",
    "prior_accessible_value_share",
    "prior_supplier_awards_log",
    "prior_supplier_profile_fit_log",
    "prior_buyer_awards_log",
    "description_term_count_log",
]
VALUE_FEATURE_NAMES = [
    "profile_term_overlap",
    "skill_match_ratio",
    "good_fit_overlap",
    "bad_fit_overlap",
    "missing_capability_overlap",
    "top_division_match",
    "category_construction",
    "category_professional",
    "category_goods",
    "type_rfq_or_quotation",
    "type_tender",
    "type_rfp",
    "type_rfsq",
    "prior_segment_awards_log",
    "prior_segment_supplier_log",
    "prior_top_supplier_share",
    "prior_segment_median_value_ratio",
    "prior_accessible_value_share",
    "prior_supplier_awards_log",
    "prior_supplier_profile_fit_log",
    "prior_buyer_awards_log",
    "description_term_count_log",
    "award_year_norm",
    "award_month_sin",
    "award_month_cos",
]


@dataclass(frozen=True)
class RankerExample:
    profile_id: str
    document_number: str
    label: str
    target: int
    hard_negative: bool
    features: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MarketExample:
    profile_id: str
    document_number: str
    supplier: str
    award_date: str
    award_value: float
    label: str
    target: int
    hard_negative: bool
    features: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrainedMarketModel:
    profile_id: str
    model: Any
    summary: dict[str, Any]
    value_model: Any | None = None
    value_summary: dict[str, Any] | None = None


def build_ranker_examples(
    profile: BusinessProfile,
    solicitations: list[Solicitation],
    awards: list[AwardRecord],
    today: Any,
) -> list[RankerExample]:
    evaluated = evaluate_opportunities(profile, solicitations, awards, today=today)
    return [example_from_opportunity(profile, item) for item in evaluated]


def build_historical_award_examples(
    profile: BusinessProfile,
    awards: list[AwardRecord],
    negative_ratio: int = 3,
) -> list[RankerExample]:
    positives: list[RankerExample] = []
    negatives: list[RankerExample] = []
    seen_awards: set[str] = set()
    profile_terms = meaningful_terms(
        " ".join([profile.business_type, *profile.skills, *profile.good_fit_examples])
    )
    for award in awards:
        award_key = (award.document_number or "").strip() or _award_text(award)
        if award_key in seen_awards:
            continue
        seen_awards.add(award_key)
        score, _ = _profile_award_fit(profile, award)
        target = 1 if score > 0 else 0
        text_terms = meaningful_terms(_award_text(award))
        hard_negative = bool(not target and profile_terms & text_terms)
        example = example_from_award(profile, award, target=target, hard_negative=hard_negative)
        if target:
            positives.append(example)
        elif hard_negative:
            negatives.append(example)

    negative_limit = max(50, len(positives) * max(1, negative_ratio))
    sampled_negatives = sorted(
        negatives,
        key=lambda item: (_stable_bucket(f"{item.profile_id}:{item.document_number}", 10000), item.document_number),
    )[:negative_limit]
    return positives + sampled_negatives


def build_market_award_examples(
    profile: BusinessProfile,
    awards: list[AwardRecord],
    negative_ratio: int = 8,
) -> list[MarketExample]:
    """Build a time-aware award-history training set.

    Features are computed from profile text, award metadata, and awards that happened
    before the current award date. That keeps supplier/market signals useful without
    letting future awards leak into the example.
    """

    positives: list[MarketExample] = []
    hard_negatives: list[MarketExample] = []
    easy_negatives: list[MarketExample] = []
    context = _new_market_context()
    profile_terms = meaningful_terms(
        " ".join([profile.business_type, *profile.skills, *profile.good_fit_examples])
    )

    sorted_awards = sorted(
        awards,
        key=lambda item: (
            item.award_date or date.min,
            item.document_number,
            item.supplier,
            item.award_value,
        ),
    )
    index = 0
    while index < len(sorted_awards):
        award_date = sorted_awards[index].award_date or date.min
        same_day: list[AwardRecord] = []
        while index < len(sorted_awards) and (sorted_awards[index].award_date or date.min) == award_date:
            same_day.append(sorted_awards[index])
            index += 1

        pending_updates: list[tuple[AwardRecord, int]] = []
        seen_same_day: set[str] = set()
        for award in same_day:
            award_key = _market_award_key(award)
            if award_key in seen_same_day:
                continue
            seen_same_day.add(award_key)
            fit_score, _ = _profile_award_fit(profile, award)
            target = 1 if fit_score > 0 else 0
            pending_updates.append((award, target))

            text_terms = meaningful_terms(_award_text(award))
            hard_negative = bool(
                not target
                and (
                    profile_terms & text_terms
                    or award.division in set(profile.top_divisions)
                )
            )
            example = MarketExample(
                profile_id=profile.profile_id,
                document_number=f"AWARD:{award.document_number}",
                supplier=award.supplier,
                award_date=award.award_date.isoformat() if award.award_date else "",
                award_value=float(award.award_value),
                label="FutureProfileAward" if target else "OtherAward",
                target=target,
                hard_negative=hard_negative,
                features=extract_market_award_features(profile, award, context),
            )
            if target:
                positives.append(example)
            elif hard_negative:
                hard_negatives.append(example)
            else:
                easy_negatives.append(example)

        for award, target in pending_updates:
            _update_market_context(profile, award, target, context)

    easy_limit = max(100, len(positives) * max(1, negative_ratio))
    sampled_easy = sorted(
        easy_negatives,
        key=lambda item: (
            _stable_bucket(f"{item.profile_id}:{item.document_number}:{item.supplier}", 10000),
            item.document_number,
            item.supplier,
        ),
    )[:easy_limit]
    return positives + hard_negatives + sampled_easy


def train_award_history_market_model(
    profile: BusinessProfile,
    awards: list[AwardRecord],
) -> TrainedMarketModel:
    require_sklearn()
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    examples = build_market_award_examples(profile=profile, awards=awards)
    if len({example.target for example in examples}) < 2:
        raise RuntimeError(
            "Award-history market model requires at least one positive and one negative "
            "training example from the local award history."
        )

    train_examples, test_examples = temporal_market_split(examples)
    if len({example.target for example in train_examples}) < 2:
        raise RuntimeError(
            "Award-history market model temporal training split has only one class. "
            "Refresh or expand award history before running the scan."
        )

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42),
    )
    model.fit(
        market_feature_matrix(train_examples),
        market_target_vector(train_examples),
        logisticregression__sample_weight=market_sample_weights(train_examples),
    )
    test_scores = [
        float(score)
        for score in model.predict_proba(market_feature_matrix(test_examples))[:, 1]
    ]
    summary = market_evaluation_summary(examples, train_examples, test_examples, test_scores, model)
    value_model, value_summary = train_award_value_model(examples)
    summary["value_model"] = value_summary
    return TrainedMarketModel(
        profile_id=profile.profile_id,
        model=model,
        summary=summary,
        value_model=value_model,
        value_summary=value_summary,
    )


def apply_market_intelligence(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
    awards: list[AwardRecord],
    trained_model: TrainedMarketModel,
    today: date,
    priority_mode: str = "best_win_chance",
) -> list[EvaluatedOpportunity]:
    context = _market_context_for_awards(profile, awards, today)
    value_context = _award_value_context_for_awards(profile, awards, today)
    model = trained_model.model
    for opportunity in opportunities:
        if opportunity.label == "Skip":
            opportunity.market_fit = MarketFitSignal(
                source="skipped_by_bid_gates",
                score=0.0,
                confidence="Skipped",
                summary="Skipped before award-history market scoring because deterministic bid gates found a blocker.",
                evidence=list(opportunity.rejection_reasons[:3]),
                model_metrics={
                    "mode": trained_model.summary.get("mode", "sklearn_award_history"),
                    "examples": trained_model.summary.get("examples", 0),
                },
            )
            opportunity.fit_probability = 0.0
            opportunity.bid_recommendation = BidRecommendation(
                source="skipped_by_bid_gates",
                basis="deterministic bid gates rejected this listing before value estimation",
                evidence=list(opportunity.rejection_reasons[:3]),
            )
            opportunity.model_explanation = ModelExplanation(
                source="skipped_by_bid_gates",
                model_type="not_scored",
                evidence=["Skipped listings are not sent through market/value scoring during the main scan."],
            )
            continue
        features = extract_market_opportunity_features(profile, opportunity, context)
        score = float(model.predict_proba([[features.get(name, 0.0) for name in MARKET_FEATURE_NAMES]])[0][1])
        signal = _market_signal_from_score(opportunity, features, score, trained_model)
        opportunity.market_fit = signal
        opportunity.fit_probability = round(score, 4)
        value_features = extract_value_opportunity_features(profile, opportunity, context, today)
        opportunity.bid_recommendation = _bid_recommendation_from_model(
            profile=profile,
            opportunity=opportunity,
            value_features=value_features,
            trained_model=trained_model,
            value_context=value_context,
        )
        opportunity.predicted_bid = opportunity.bid_recommendation.recommended_bid
        opportunity.bid_range_low = opportunity.bid_recommendation.low_bid
        opportunity.bid_range_high = opportunity.bid_recommendation.high_bid
        opportunity.model_explanation = _model_explanation_from_features(
            trained_model=trained_model,
            opportunity_features=features,
            value_features=value_features,
        )
        _attach_market_signal_to_trace(opportunity, signal)
        _attach_bid_recommendation_to_trace(opportunity)

    return sorted(
        opportunities,
        key=lambda item: _market_sort_key(item, priority_mode),
    )


def estimate_bid_recommendation(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    awards: list[AwardRecord],
    today: date,
) -> BidRecommendation:
    return _bid_recommendation_from_context(
        profile,
        opportunity,
        _award_value_context_for_awards(profile, awards, today),
    )


def ranker_status() -> dict[str, Any]:
    try:
        require_sklearn()
        import sklearn
    except RuntimeError as exc:
        return {
            "available": False,
            "mode": "missing_dependencies",
            "error": str(exc),
        }
    return {
        "available": True,
        "mode": "sklearn_award_history",
        "version": getattr(sklearn, "__version__", "unknown"),
        "fallback": "none",
    }


def value_model_status() -> dict[str, Any]:
    try:
        __import__("cuml")
        return {"available": True, "mode": "rapids_cuml_available", "preferred": "gpu"}
    except Exception:
        pass
    try:
        __import__("xgboost")
        return {"available": True, "mode": "xgboost_available", "preferred": "gpu_if_cuda_available"}
    except Exception:
        pass
    try:
        require_sklearn()
        return {"available": True, "mode": "sklearn_random_forest_fallback", "preferred": "cpu"}
    except RuntimeError as exc:
        return {"available": False, "mode": "missing_dependencies", "error": str(exc)}


def _new_value_regressor() -> tuple[Any, str]:
    try:
        from xgboost import XGBRegressor  # type: ignore[import-not-found]

        return (
            XGBRegressor(
                n_estimators=140,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.85,
                colsample_bytree=0.85,
                objective="reg:squarederror",
                random_state=42,
                tree_method="hist",
            ),
            "xgboost_regression",
        )
    except Exception:
        pass

    from sklearn.ensemble import RandomForestRegressor

    return (
        RandomForestRegressor(
            n_estimators=120,
            max_depth=9,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=1,
        ),
        "sklearn_random_forest_regression",
    )


def example_from_opportunity(profile: BusinessProfile, opportunity: EvaluatedOpportunity) -> RankerExample:
    target = 1 if opportunity.label in ACTIONABLE_TRAINING_LABELS else 0
    hard_negative = bool(opportunity.label == "Skip" and looks_like_false_positive(opportunity))
    return RankerExample(
        profile_id=profile.profile_id,
        document_number=opportunity.solicitation.document_number,
        label=opportunity.label,
        target=target,
        hard_negative=hard_negative,
        features=extract_ranker_features(profile, opportunity),
    )


def example_from_award(
    profile: BusinessProfile,
    award: AwardRecord,
    target: int,
    hard_negative: bool,
) -> RankerExample:
    return RankerExample(
        profile_id=profile.profile_id,
        document_number=f"AWARD:{award.document_number}",
        label="HistoricalFit" if target else "HistoricalSkip",
        target=target,
        hard_negative=hard_negative,
        features=extract_award_features(profile, award, target),
    )


def extract_ranker_features(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
) -> dict[str, float]:
    solicitation = opportunity.solicitation
    text = " ".join(
        [
            solicitation.solicitation_type,
            solicitation.category,
            solicitation.description,
            solicitation.division,
        ]
    )
    text_terms = meaningful_terms(text)
    profile_terms = meaningful_terms(
        " ".join([profile.business_type, *profile.skills, *profile.good_fit_examples])
    )
    good_terms = meaningful_terms(" ".join(profile.good_fit_examples))
    bad_terms = meaningful_terms(" ".join(profile.bad_fit_examples + profile.missing_capabilities))
    type_text = solicitation.solicitation_type.lower()
    deadline = _deadline_bucket(opportunity.days_until_deadline)
    capacity = opportunity.capacity_assessment
    trace = opportunity.bid_fitness_trace
    brief = opportunity.opportunity_brief

    historical_ratio = 0.0
    if profile.max_contract_value > 0 and opportunity.historical.award_median > 0:
        historical_ratio = min(3.0, opportunity.historical.award_median / profile.max_contract_value)

    features = {
        "matched_term_count": float(len(set(opportunity.matched_terms))),
        "skill_match_ratio": _safe_ratio(len(set(opportunity.matched_terms)), len(profile.skills)),
        "good_fit_overlap": float(len(good_terms & text_terms)),
        "bad_fit_overlap": float(len(bad_terms & text_terms)),
        "top_division_match": 1.0 if solicitation.division in set(profile.top_divisions) else 0.0,
        "profile_category_overlap": float(len(profile_terms & text_terms)),
        "missing_requirement_count": float(len(set(opportunity.missing_requirements))),
        "rejection_reason_count": float(len(set(opportunity.rejection_reasons))),
        "trace_hard_blocker_count": float(len(trace.hard_blockers)),
        "trace_soft_warning_count": float(len(trace.soft_warnings)),
        "trace_positive_signal_count": float(len(trace.positive_signals)),
        "historical_similar_log": math.log1p(max(0, opportunity.historical.similar_count)),
        "historical_award_median_ratio": historical_ratio,
        "historical_accessible": 1.0 if "accessible" in opportunity.historical.accessibility.lower() else 0.0,
        "deadline_manageable": 1.0 if deadline == "manageable" else 0.0,
        "deadline_tight": 1.0 if deadline == "tight" else 0.0,
        "deadline_critical": 1.0 if deadline == "critical" else 0.0,
        "deadline_unknown": 1.0 if deadline == "unknown" else 0.0,
        "days_until_deadline_clipped": _days_feature(opportunity.days_until_deadline),
        "type_rfq_or_quotation": 1.0 if ("rfq" in type_text or "quotation" in type_text) else 0.0,
        "type_tender": 1.0 if "tender" in type_text else 0.0,
        "type_rfp": 1.0 if ("rfp" in type_text or "proposal" in type_text) else 0.0,
        "type_rfsq": 1.0 if ("rfsq" in type_text or "supplier qualification" in type_text) else 0.0,
        "pursuit_load_clear": 1.0 if capacity.pursuit_load == "Clear" else 0.0,
        "pursuit_load_busy": 1.0 if capacity.pursuit_load == "Busy" else 0.0,
        "pursuit_load_overloaded": 1.0 if capacity.pursuit_load == "Overloaded" else 0.0,
        "response_enough_time": 1.0 if capacity.response_capacity == "Enough Time" else 0.0,
        "response_tight": 1.0 if capacity.response_capacity == "Tight" else 0.0,
        "response_at_risk": 1.0 if capacity.response_capacity == "At Risk" else 0.0,
        "execution_fits_team": 1.0 if capacity.execution_capacity == "Fits Team" else 0.0,
        "execution_needs_review": 1.0 if capacity.execution_capacity == "Needs Scheduling Review" else 0.0,
        "execution_likely_too_large": 1.0 if capacity.execution_capacity == "Likely Too Large" else 0.0,
        "recommended_pursue_now": 1.0 if capacity.recommended_action == "Pursue Now" else 0.0,
        "recommended_pursue_after_review": 1.0 if capacity.recommended_action == "Pursue After Review" else 0.0,
        "recommended_monitor": 1.0 if capacity.recommended_action == "Monitor" else 0.0,
        "recommended_skip": 1.0 if capacity.recommended_action.startswith("Skip") else 0.0,
        "nemotron_blocker_count": float(len(brief.blockers) + len(brief.missing_items)),
        "requirement_document_count": float(len(opportunity.requirements.documents) + len(brief.required_documents)),
    }
    return {name: float(features.get(name, 0.0)) for name in FEATURE_NAMES}


def extract_award_features(
    profile: BusinessProfile,
    award: AwardRecord,
    target: int,
) -> dict[str, float]:
    text = _award_text(award)
    text_terms = meaningful_terms(text)
    profile_terms = meaningful_terms(
        " ".join([profile.business_type, *profile.skills, *profile.good_fit_examples])
    )
    good_terms = meaningful_terms(" ".join(profile.good_fit_examples))
    bad_terms = meaningful_terms(" ".join(profile.bad_fit_examples + profile.missing_capabilities))
    matched_skills = _matched_skill_count(profile, text_terms, text.lower())
    type_text = award.solicitation_type.lower()
    award_ratio = min(3.0, award.award_value / profile.max_contract_value) if profile.max_contract_value else 0.0
    likely_too_large = bool(award.award_value and award.award_value > profile.max_contract_value * 1.5)
    needs_review = bool(award.award_value and profile.max_contract_value < award.award_value <= profile.max_contract_value * 1.5)
    features = {
        "matched_term_count": float(matched_skills),
        "skill_match_ratio": _safe_ratio(matched_skills, len(profile.skills)),
        "good_fit_overlap": float(len(good_terms & text_terms)),
        "bad_fit_overlap": float(len(bad_terms & text_terms)),
        "top_division_match": 1.0 if award.division in set(profile.top_divisions) else 0.0,
        "profile_category_overlap": float(len(profile_terms & text_terms)),
        "missing_requirement_count": 0.0 if target else float(len(bad_terms & text_terms)),
        "rejection_reason_count": 0.0 if target else 1.0,
        "trace_hard_blocker_count": 0.0 if target else 1.0,
        "trace_soft_warning_count": 1.0 if needs_review else 0.0,
        "trace_positive_signal_count": float(min(5, matched_skills + int(target))),
        "historical_similar_log": math.log1p(1 if target else 0),
        "historical_award_median_ratio": award_ratio,
        "historical_accessible": 1.0 if target and not likely_too_large else 0.0,
        "deadline_manageable": 0.0,
        "deadline_tight": 0.0,
        "deadline_critical": 0.0,
        "deadline_unknown": 1.0,
        "days_until_deadline_clipped": 0.0,
        "type_rfq_or_quotation": 1.0 if ("rfq" in type_text or "quotation" in type_text) else 0.0,
        "type_tender": 1.0 if "tender" in type_text else 0.0,
        "type_rfp": 1.0 if ("rfp" in type_text or "proposal" in type_text) else 0.0,
        "type_rfsq": 1.0 if ("rfsq" in type_text or "supplier qualification" in type_text) else 0.0,
        "pursuit_load_clear": 1.0,
        "pursuit_load_busy": 0.0,
        "pursuit_load_overloaded": 0.0,
        "response_enough_time": 0.0,
        "response_tight": 0.0,
        "response_at_risk": 0.0,
        "execution_fits_team": 1.0 if target and not needs_review and not likely_too_large else 0.0,
        "execution_needs_review": 1.0 if needs_review else 0.0,
        "execution_likely_too_large": 1.0 if likely_too_large else 0.0,
        "recommended_pursue_now": 1.0 if target and not needs_review else 0.0,
        "recommended_pursue_after_review": 1.0 if target and needs_review else 0.0,
        "recommended_monitor": 0.0,
        "recommended_skip": 1.0 if not target else 0.0,
        "nemotron_blocker_count": 0.0,
        "requirement_document_count": 0.0,
    }
    return {name: float(features.get(name, 0.0)) for name in FEATURE_NAMES}


def extract_market_award_features(
    profile: BusinessProfile,
    award: AwardRecord,
    context: dict[str, Any] | None = None,
) -> dict[str, float]:
    market_context = context or _new_market_context()
    text = _award_text(award)
    text_lower = text.lower()
    text_terms = meaningful_terms(text)
    profile_terms = meaningful_terms(
        " ".join([profile.business_type, *profile.skills, *profile.good_fit_examples])
    )
    good_terms = meaningful_terms(" ".join(profile.good_fit_examples))
    bad_terms = meaningful_terms(" ".join(profile.bad_fit_examples))
    missing_terms = meaningful_terms(" ".join(profile.missing_capabilities))
    matched_skills = _matched_skill_count(profile, text_terms, text_lower)
    type_text = award.solicitation_type.lower()
    category = _category_family(award.category)
    award_ratio = min(5.0, award.award_value / profile.max_contract_value) if profile.max_contract_value else 0.0
    segment_snapshot = _market_context_snapshot(profile, award, market_context)

    features = {
        "profile_term_overlap": float(len(profile_terms & text_terms)),
        "skill_match_ratio": _safe_ratio(matched_skills, len(profile.skills)),
        "good_fit_overlap": float(len(good_terms & text_terms)),
        "bad_fit_overlap": float(len(bad_terms & text_terms)),
        "missing_capability_overlap": float(len(missing_terms & text_terms)),
        "top_division_match": 1.0 if award.division in set(profile.top_divisions) else 0.0,
        "category_construction": 1.0 if category == "construction" else 0.0,
        "category_professional": 1.0 if category == "professional" else 0.0,
        "category_goods": 1.0 if category == "goods" else 0.0,
        "type_rfq_or_quotation": 1.0 if ("rfq" in type_text or "quotation" in type_text) else 0.0,
        "type_tender": 1.0 if "tender" in type_text else 0.0,
        "type_rfp": 1.0 if ("rfp" in type_text or "proposal" in type_text) else 0.0,
        "type_rfsq": 1.0 if ("rfsq" in type_text or "supplier qualification" in type_text) else 0.0,
        "award_value_log": math.log1p(max(0.0, award.award_value)),
        "award_value_to_capacity": award_ratio,
        "award_under_capacity": 1.0 if 0 < award.award_value <= profile.max_contract_value else 0.0,
        "award_partner_band": 1.0 if profile.max_contract_value < award.award_value <= profile.max_contract_value * 1.5 else 0.0,
        "award_too_large": 1.0 if award.award_value > profile.max_contract_value * 1.5 else 0.0,
        "prior_segment_awards_log": math.log1p(segment_snapshot["segment_awards"]),
        "prior_segment_supplier_log": math.log1p(segment_snapshot["segment_supplier_count"]),
        "prior_top_supplier_share": segment_snapshot["top_supplier_share"],
        "prior_segment_median_value_ratio": segment_snapshot["median_value_ratio"],
        "prior_accessible_value_share": segment_snapshot["accessible_value_share"],
        "prior_supplier_awards_log": math.log1p(segment_snapshot["supplier_awards"]),
        "prior_supplier_profile_fit_log": math.log1p(segment_snapshot["supplier_profile_fit_awards"]),
        "prior_buyer_awards_log": math.log1p(segment_snapshot["buyer_awards"]),
        "description_term_count_log": math.log1p(len(text_terms)),
    }
    return {name: float(features.get(name, 0.0)) for name in MARKET_FEATURE_NAMES}


def extract_market_opportunity_features(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    context: dict[str, Any] | None = None,
) -> dict[str, float]:
    market_context = context or _new_market_context()
    solicitation = opportunity.solicitation
    text = " ".join(
        [
            solicitation.solicitation_type,
            solicitation.category,
            solicitation.division,
            solicitation.description,
        ]
    )
    text_terms = meaningful_terms(text)
    text_lower = text.lower()
    profile_terms = meaningful_terms(
        " ".join([profile.business_type, *profile.skills, *profile.good_fit_examples])
    )
    good_terms = meaningful_terms(" ".join(profile.good_fit_examples))
    bad_terms = meaningful_terms(" ".join(profile.bad_fit_examples))
    missing_terms = meaningful_terms(" ".join(profile.missing_capabilities))
    matched_skills = _matched_skill_count(profile, text_terms, text_lower)
    type_text = solicitation.solicitation_type.lower()
    category = _category_family(solicitation.category)
    estimated_value = (
        opportunity.historical.award_median
        or opportunity.historical.award_max
        or opportunity.historical.award_min
        or 0.0
    )
    value_ratio = min(5.0, estimated_value / profile.max_contract_value) if profile.max_contract_value else 0.0
    segment_snapshot = _market_context_snapshot_for_values(
        profile=profile,
        category=solicitation.category,
        solicitation_type=solicitation.solicitation_type,
        division=solicitation.division,
        supplier="",
        buyer=solicitation.buyer_name,
        context=market_context,
    )

    features = {
        "profile_term_overlap": float(len(profile_terms & text_terms)),
        "skill_match_ratio": _safe_ratio(matched_skills, len(profile.skills)),
        "good_fit_overlap": float(len(good_terms & text_terms)),
        "bad_fit_overlap": float(len(bad_terms & text_terms)),
        "missing_capability_overlap": float(len(missing_terms & text_terms)),
        "top_division_match": 1.0 if solicitation.division in set(profile.top_divisions) else 0.0,
        "category_construction": 1.0 if category == "construction" else 0.0,
        "category_professional": 1.0 if category == "professional" else 0.0,
        "category_goods": 1.0 if category == "goods" else 0.0,
        "type_rfq_or_quotation": 1.0 if ("rfq" in type_text or "quotation" in type_text) else 0.0,
        "type_tender": 1.0 if "tender" in type_text else 0.0,
        "type_rfp": 1.0 if ("rfp" in type_text or "proposal" in type_text) else 0.0,
        "type_rfsq": 1.0 if ("rfsq" in type_text or "supplier qualification" in type_text) else 0.0,
        "award_value_log": math.log1p(max(0.0, estimated_value)),
        "award_value_to_capacity": value_ratio,
        "award_under_capacity": 1.0 if 0 < estimated_value <= profile.max_contract_value else 0.0,
        "award_partner_band": 1.0 if profile.max_contract_value < estimated_value <= profile.max_contract_value * 1.5 else 0.0,
        "award_too_large": 1.0 if estimated_value > profile.max_contract_value * 1.5 else 0.0,
        "prior_segment_awards_log": math.log1p(segment_snapshot["segment_awards"]),
        "prior_segment_supplier_log": math.log1p(segment_snapshot["segment_supplier_count"]),
        "prior_top_supplier_share": segment_snapshot["top_supplier_share"],
        "prior_segment_median_value_ratio": segment_snapshot["median_value_ratio"],
        "prior_accessible_value_share": segment_snapshot["accessible_value_share"],
        "prior_supplier_awards_log": 0.0,
        "prior_supplier_profile_fit_log": 0.0,
        "prior_buyer_awards_log": math.log1p(segment_snapshot["buyer_awards"]),
        "description_term_count_log": math.log1p(len(text_terms)),
    }
    return {name: float(features.get(name, 0.0)) for name in MARKET_FEATURE_NAMES}


def extract_value_example_features(example: MarketExample) -> dict[str, float]:
    features = dict(example.features)
    award_date = _parse_iso_date(example.award_date)
    month = award_date.month if award_date else 1
    year = award_date.year if award_date else 2020
    features.update(
        {
            "award_year_norm": max(0.0, min(1.0, (year - 2018) / 10.0)),
            "award_month_sin": math.sin((month / 12.0) * math.tau),
            "award_month_cos": math.cos((month / 12.0) * math.tau),
        }
    )
    return {name: float(features.get(name, 0.0)) for name in VALUE_FEATURE_NAMES}


def extract_value_opportunity_features(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    context: dict[str, Any] | None,
    today: date,
) -> dict[str, float]:
    features = extract_market_opportunity_features(profile, opportunity, context)
    rag = opportunity.rag_evidence
    month = (opportunity.solicitation.issue_date or today).month
    year = (opportunity.solicitation.issue_date or today).year
    if rag.value_median and profile.max_contract_value:
        features["prior_segment_median_value_ratio"] = min(5.0, rag.value_median / profile.max_contract_value)
    features.update(
        {
            "award_year_norm": max(0.0, min(1.0, (year - 2018) / 10.0)),
            "award_month_sin": math.sin((month / 12.0) * math.tau),
            "award_month_cos": math.cos((month / 12.0) * math.tau),
        }
    )
    return {name: float(features.get(name, 0.0)) for name in VALUE_FEATURE_NAMES}


def feature_matrix(examples: list[RankerExample]) -> list[list[float]]:
    return [[example.features.get(name, 0.0) for name in FEATURE_NAMES] for example in examples]


def market_feature_matrix(examples: list[MarketExample]) -> list[list[float]]:
    return [[example.features.get(name, 0.0) for name in MARKET_FEATURE_NAMES] for example in examples]


def value_feature_matrix(examples: list[MarketExample]) -> list[list[float]]:
    return [[extract_value_example_features(example).get(name, 0.0) for name in VALUE_FEATURE_NAMES] for example in examples]


def target_vector(examples: list[RankerExample]) -> list[int]:
    return [example.target for example in examples]


def market_target_vector(examples: list[MarketExample]) -> list[int]:
    return [example.target for example in examples]


def value_target_vector(examples: list[MarketExample]) -> list[float]:
    return [math.log1p(max(0.0, example.award_value)) for example in examples]


def sample_weights(examples: list[RankerExample]) -> list[float]:
    weights = []
    positive_count = sum(example.target for example in examples)
    negative_count = max(1, len(examples) - positive_count)
    positive_weight = max(1.0, negative_count / max(1, positive_count))
    for example in examples:
        if example.target:
            weights.append(positive_weight)
        elif example.hard_negative:
            weights.append(2.0)
        else:
            weights.append(1.0)
    return weights


def market_sample_weights(examples: list[MarketExample]) -> list[float]:
    weights = []
    positive_count = sum(example.target for example in examples)
    negative_count = max(1, len(examples) - positive_count)
    positive_weight = max(1.0, negative_count / max(1, positive_count))
    for example in examples:
        if example.target:
            weights.append(positive_weight)
        elif example.hard_negative:
            weights.append(2.5)
        else:
            weights.append(1.0)
    return weights


def train_award_value_model(examples: list[MarketExample]) -> tuple[Any | None, dict[str, Any]]:
    value_examples = [
        example
        for example in examples
        if example.target and example.award_value > 0
    ]
    if len(value_examples) < 8:
        return None, {
            "status": "fallback",
            "mode": "historical_average",
            "examples": len(value_examples),
            "reason": "Award-value regression needs at least 8 positive historical awards.",
        }

    train_examples, test_examples = temporal_market_split(value_examples)
    if not test_examples:
        split_at = max(1, int(len(value_examples) * 0.8))
        train_examples, test_examples = value_examples[:split_at], value_examples[split_at:]
    model, mode = _new_value_regressor()
    model.fit(value_feature_matrix(train_examples), value_target_vector(train_examples))
    predictions = [math.expm1(float(value)) for value in model.predict(value_feature_matrix(test_examples))]
    actuals = [example.award_value for example in test_examples]
    mae = sum(abs(predicted - actual) for predicted, actual in zip(predictions, actuals)) / max(1, len(actuals))
    mape = sum(
        abs(predicted - actual) / max(1.0, actual)
        for predicted, actual in zip(predictions, actuals)
    ) / max(1, len(actuals))
    return model, {
        "status": "trained",
        "mode": mode,
        "purpose": "Award-value regression trained on historical positive profile-award examples.",
        "examples": len(value_examples),
        "training_examples": len(train_examples),
        "test_examples": len(test_examples),
        "training_award_date_range": _market_date_range(train_examples),
        "test_award_date_range": _market_date_range(test_examples),
        "mae": round(mae, 2),
        "mape": round(mape, 4),
        "feature_names": VALUE_FEATURE_NAMES,
    }


def temporal_market_split(examples: list[MarketExample]) -> tuple[list[MarketExample], list[MarketExample]]:
    dated = [example for example in examples if example.award_date]
    if dated:
        train = [example for example in dated if example.award_date < "2024-01-01"]
        test = [example for example in dated if example.award_date >= "2024-01-01"]
        if train and test and len({example.target for example in train}) >= 2:
            return train, test

    ordered = sorted(
        examples,
        key=lambda item: (
            item.award_date or "",
            item.profile_id,
            item.document_number,
            item.supplier,
        ),
    )
    split_at = max(1, int(len(ordered) * 0.75))
    return ordered[:split_at], ordered[split_at:]


def market_evaluation_summary(
    examples: list[MarketExample],
    train_examples: list[MarketExample],
    test_examples: list[MarketExample],
    test_scores: list[float],
    model: Any,
) -> dict[str, Any]:
    test_targets = market_target_vector(test_examples)
    positive_count = sum(example.target for example in examples)
    test_positive_count = sum(test_targets)
    base_positive_rate = _safe_ratio(test_positive_count, len(test_examples))
    top_decile_size = max(1, int(len(test_examples) * 0.1))
    top_decile_precision = _precision_at_k(test_examples, test_scores, top_decile_size)
    roc_auc = _safe_roc_auc(test_targets, test_scores)
    return {
        "status": "trained",
        "mode": "sklearn_award_history",
        "purpose": "Temporal award-history market-fit model trained on older awards and tested on recent awards.",
        "examples": len(examples),
        "training_examples": len(train_examples),
        "test_examples": len(test_examples),
        "positive_examples": positive_count,
        "negative_examples": len(examples) - positive_count,
        "hard_negative_examples": sum(1 for example in examples if example.hard_negative),
        "training_award_date_range": _market_date_range(train_examples),
        "test_award_date_range": _market_date_range(test_examples),
        "test_positive_rate": round(base_positive_rate, 4),
        "average_precision": round(_safe_average_precision(test_targets, test_scores), 4),
        "roc_auc": round(roc_auc, 4) if roc_auc is not None else None,
        "precision_at_10": round(_precision_at_k(test_examples, test_scores, 10), 4),
        "recall_at_10": round(_recall_at_k(test_examples, test_scores, 10), 4),
        "precision_at_20": round(_precision_at_k(test_examples, test_scores, 20), 4),
        "hard_negative_rate_top_20": round(_hard_negative_rate_at_k(test_examples, test_scores, 20), 4),
        "top_decile_precision": round(top_decile_precision, 4),
        "top_decile_lift": round(top_decile_precision / base_positive_rate, 2) if base_positive_rate else None,
        "top_weighted_features": top_weighted_features(model, MARKET_FEATURE_NAMES),
        "profile_metrics": _market_profile_metrics(test_examples, test_scores),
        "supplier_intelligence": supplier_intelligence(examples),
    }


def top_weighted_features(
    model: Any,
    feature_names: list[str],
    limit: int = 8,
) -> list[dict[str, Any]]:
    classifier = model.named_steps["logisticregression"]
    weights = classifier.coef_[0]
    ranked = sorted(
        zip(feature_names, weights),
        key=lambda item: abs(float(item[1])),
        reverse=True,
    )
    return [
        {"feature": name, "weight": round(float(weight), 4)}
        for name, weight in ranked[:limit]
    ]


def supplier_intelligence(examples: list[MarketExample]) -> list[dict[str, Any]]:
    by_profile: dict[str, list[MarketExample]] = {}
    for example in examples:
        if example.target:
            by_profile.setdefault(example.profile_id, []).append(example)

    summaries = []
    for profile_id, rows in sorted(by_profile.items()):
        supplier_counts: dict[str, int] = {}
        for example in rows:
            supplier = example.supplier.strip() or "Unknown supplier"
            supplier_counts[supplier] = supplier_counts.get(supplier, 0) + 1
        top_suppliers = sorted(supplier_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
        total = len(rows)
        summaries.append(
            {
                "profile_id": profile_id,
                "fit_awards": total,
                "distinct_fit_suppliers": len(supplier_counts),
                "repeat_supplier_count": sum(1 for count in supplier_counts.values() if count > 1),
                "top_supplier_share": round(top_suppliers[0][1] / total, 4) if total and top_suppliers else 0.0,
                "top_suppliers": [
                    {"supplier": supplier, "fit_awards": count}
                    for supplier, count in top_suppliers
                ],
            }
        )
    return summaries


def require_sklearn() -> None:
    try:
        __import__("sklearn")
    except Exception as exc:
        raise RuntimeError(
            "Bid ranker training requires scikit-learn. Install dependencies with "
            "`python -m pip install -r requirements.txt`."
        ) from exc


def _market_profile_metrics(examples: list[MarketExample], scores: list[float]) -> list[dict[str, Any]]:
    by_profile: dict[str, list[tuple[MarketExample, float]]] = {}
    for example, score in zip(examples, scores):
        by_profile.setdefault(example.profile_id, []).append((example, score))

    metrics = []
    for profile_id, rows in sorted(by_profile.items()):
        rows.sort(key=lambda row: row[1], reverse=True)
        targets = [row[0].target for row in rows]
        profile_scores = [row[1] for row in rows]
        positives = sum(targets)
        metrics.append(
            {
                "profile_id": profile_id,
                "test_examples": len(rows),
                "test_positives": positives,
                "precision_at_10": round(_precision_at_k([row[0] for row in rows], profile_scores, 10), 4),
                "recall_at_10": round(_recall_at_k([row[0] for row in rows], profile_scores, 10), 4),
                "average_precision": round(_safe_average_precision(targets, profile_scores), 4),
                "top_documents": [
                    {
                        "document_number": row[0].document_number,
                        "supplier": row[0].supplier,
                        "award_date": row[0].award_date,
                        "target": row[0].target,
                        "hard_negative": row[0].hard_negative,
                        "score": round(row[1], 4),
                    }
                    for row in rows[:5]
                ],
            }
        )
    return metrics


def _precision_at_k(examples: list[Any], scores: list[float], k: int) -> float:
    rows = sorted(zip(examples, scores), key=lambda row: row[1], reverse=True)[:k]
    if not rows:
        return 0.0
    return sum(row[0].target for row in rows) / len(rows)


def _recall_at_k(examples: list[Any], scores: list[float], k: int) -> float:
    positives = sum(example.target for example in examples)
    if positives <= 0:
        return 0.0
    rows = sorted(zip(examples, scores), key=lambda row: row[1], reverse=True)[:k]
    return sum(row[0].target for row in rows) / positives


def _hard_negative_rate_at_k(examples: list[Any], scores: list[float], k: int) -> float:
    rows = sorted(zip(examples, scores), key=lambda row: row[1], reverse=True)[:k]
    if not rows:
        return 0.0
    return sum(1 for row in rows if row[0].hard_negative) / len(rows)


def _market_date_range(examples: list[MarketExample]) -> dict[str, str | None]:
    dates = sorted(example.award_date for example in examples if example.award_date)
    if not dates:
        return {"start": None, "end": None}
    return {"start": dates[0], "end": dates[-1]}


def _safe_average_precision(targets: list[int], scores: list[float]) -> float:
    from sklearn.metrics import average_precision_score

    if not targets or len(set(targets)) < 2:
        return 0.0
    return float(average_precision_score(targets, scores))


def _safe_roc_auc(targets: list[int], scores: list[float]) -> float | None:
    from sklearn.metrics import roc_auc_score

    if not targets or len(set(targets)) < 2:
        return None
    return float(roc_auc_score(targets, scores))


def _deadline_bucket(days_until_deadline: int | None) -> str:
    if days_until_deadline is None:
        return "unknown"
    if days_until_deadline < 5:
        return "critical"
    if days_until_deadline <= 10:
        return "tight"
    return "manageable"


def _days_feature(days_until_deadline: int | None) -> float:
    if days_until_deadline is None:
        return 0.0
    return max(0.0, min(30.0, float(days_until_deadline))) / 30.0


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return min(1.0, max(0.0, numerator / denominator))


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _award_text(award: AwardRecord) -> str:
    return " ".join([award.solicitation_type, award.category, award.division, award.description])


def _matched_skill_count(profile: BusinessProfile, text_terms: set[str], text_lower: str) -> int:
    count = 0
    for skill in profile.skills:
        skill_text = skill.lower().strip()
        skill_terms = meaningful_terms(skill_text)
        if not skill_terms:
            continue
        if skill_text in text_lower or len(skill_terms & text_terms) >= min(2, len(skill_terms)):
            count += 1
    return count


def _market_context_for_awards(
    profile: BusinessProfile,
    awards: list[AwardRecord],
    today: date,
) -> dict[str, Any]:
    context = _new_market_context()
    seen: set[str] = set()
    for award in sorted(
        awards,
        key=lambda item: (
            item.award_date or date.min,
            item.document_number,
            item.supplier,
            item.award_value,
        ),
    ):
        if award.award_date and award.award_date > today:
            continue
        award_key = _market_award_key(award)
        if award_key in seen:
            continue
        seen.add(award_key)
        target = 1 if _profile_award_fit(profile, award)[0] > 0 else 0
        _update_market_context(profile, award, target, context)
    return context


def _market_signal_from_score(
    opportunity: EvaluatedOpportunity,
    features: dict[str, float],
    score: float,
    trained_model: TrainedMarketModel,
) -> MarketFitSignal:
    summary = trained_model.summary
    score_percent = round(score * 100)
    confidence = _market_confidence(score)
    market_size = int(round(math.expm1(features.get("prior_segment_awards_log", 0.0))))
    supplier_count = int(round(math.expm1(features.get("prior_segment_supplier_log", 0.0))))
    top_supplier_share = float(features.get("prior_top_supplier_share", 0.0))
    accessible_share = float(features.get("prior_accessible_value_share", 0.0))
    median_ratio = float(features.get("prior_segment_median_value_ratio", 0.0))
    evidence = [
        (
            f"Temporal award-history model scored this opportunity at {score_percent}% market fit "
            f"({confidence.lower()})."
        ),
        (
            f"Comparable segment has {market_size} prior award(s), {supplier_count} supplier(s), "
            f"and {top_supplier_share:.0%} top-supplier concentration."
        ),
    ]
    lift = summary.get("top_decile_lift")
    if lift:
        evidence.append(
            f"Model validation used a recent-award holdout with {float(lift):.2f}x top-decile lift."
        )
    if accessible_share:
        evidence.append(f"{accessible_share:.0%} of prior segment awards were within this profile's capacity.")
    if median_ratio:
        evidence.append(f"Prior segment median value is {median_ratio:.2f}x the profile capacity.")

    return MarketFitSignal(
        source="sklearn_award_history",
        score=round(score, 4),
        confidence=confidence,
        summary=(
            f"{confidence} market signal from local award-history ML; "
            f"{score_percent}% fit probability before owner/Nemotron packet work."
        ),
        evidence=evidence,
        top_factors=_feature_contributions(trained_model.model, features),
        supplier_concentration={
            "prior_segment_awards": market_size,
            "prior_segment_suppliers": supplier_count,
            "top_supplier_share": round(top_supplier_share, 4),
            "accessible_value_share": round(accessible_share, 4),
        },
        model_metrics={
            "mode": summary.get("mode", "sklearn_award_history"),
            "examples": summary.get("examples", 0),
            "positive_examples": summary.get("positive_examples", 0),
            "precision_at_10": summary.get("precision_at_10", 0.0),
            "average_precision": summary.get("average_precision", 0.0),
            "top_decile_lift": summary.get("top_decile_lift"),
            "training_award_date_range": summary.get("training_award_date_range", {}),
            "test_award_date_range": summary.get("test_award_date_range", {}),
        },
    )


def _feature_contributions(model: Any, features: dict[str, float], limit: int = 6) -> list[dict[str, Any]]:
    classifier = model.named_steps["logisticregression"]
    weights = classifier.coef_[0]
    rows = []
    for name, weight in zip(MARKET_FEATURE_NAMES, weights):
        value = float(features.get(name, 0.0))
        if value == 0.0:
            continue
        contribution = float(weight) * value
        rows.append((name, value, float(weight), contribution))
    rows.sort(key=lambda row: abs(row[3]), reverse=True)
    return [
        {
            "feature": name,
            "value": round(value, 4),
            "weight": round(weight, 4),
            "contribution": round(contribution, 4),
        }
        for name, value, weight, contribution in rows[:limit]
    ]


def _model_explanation_from_features(
    trained_model: TrainedMarketModel,
    opportunity_features: dict[str, float],
    value_features: dict[str, float],
) -> ModelExplanation:
    value_summary = trained_model.value_summary or {}
    evidence = [
        "Fit probability comes from the temporal award-history classifier.",
        "Bid amount comes from the award-value regression model when enough historical examples exist.",
    ]
    if value_summary.get("status") == "trained":
        evidence.append(
            f"Value model holdout MAE ${float(value_summary.get('mae') or 0):,.0f}, "
            f"MAPE {float(value_summary.get('mape') or 0):.1%}."
        )
    else:
        evidence.append("Value model fell back to historical analog bands because training evidence was limited.")
    return ModelExplanation(
        source="local_award_history_models",
        model_type=f"{trained_model.summary.get('mode', 'classifier')} + {value_summary.get('mode', 'historical_fallback')}",
        feature_names=VALUE_FEATURE_NAMES,
        top_factors=_feature_contributions(trained_model.model, opportunity_features),
        metrics={
            "fit_model": {
                "precision_at_10": trained_model.summary.get("precision_at_10", 0.0),
                "average_precision": trained_model.summary.get("average_precision", 0.0),
                "top_decile_lift": trained_model.summary.get("top_decile_lift"),
            },
            "value_model": value_summary,
            "nonzero_value_features": sum(1 for name in VALUE_FEATURE_NAMES if value_features.get(name, 0.0)),
        },
        evidence=evidence,
    )


def _market_confidence(score: float) -> str:
    if score >= 0.8:
        return "Strong"
    if score >= 0.55:
        return "Promising"
    if score >= 0.3:
        return "Watch"
    return "Weak"


def _attach_market_signal_to_trace(opportunity: EvaluatedOpportunity, signal: MarketFitSignal) -> None:
    message = f"Market model: {signal.confidence} award-history signal ({round(signal.score * 100)}%)."
    if message not in opportunity.bid_fitness_trace.positive_signals:
        opportunity.bid_fitness_trace.positive_signals.append(message)
    opportunity.bid_fitness_trace.scorecard_labels["Market Fit"] = signal.confidence
    if opportunity.label != "Skip" and message not in opportunity.reasons:
        opportunity.reasons.append(message)


def _attach_bid_recommendation_to_trace(opportunity: EvaluatedOpportunity) -> None:
    recommendation = opportunity.bid_recommendation
    if not recommendation or recommendation.recommended_bid <= 0:
        return
    amount = f"${recommendation.recommended_bid:,.0f}"
    message = (
        f"Revenue bid guidance: bid around {amount} from "
        f"{recommendation.contract_type} historical award averages."
    )
    if message not in opportunity.bid_fitness_trace.positive_signals:
        opportunity.bid_fitness_trace.positive_signals.append(message)
    opportunity.bid_fitness_trace.scorecard_labels["Bid Amount"] = amount
    if opportunity.label != "Skip" and message not in opportunity.reasons:
        opportunity.reasons.append(message)


def _market_sort_key(item: EvaluatedOpportunity, priority_mode: str) -> tuple[object, ...]:
    return (
        _decision_order(item.label),
        -_market_priority_score(item, priority_mode),
        item.days_until_deadline if item.days_until_deadline is not None else 9999,
        item.solicitation.document_number,
    )


def _market_priority_score(item: EvaluatedOpportunity, priority_mode: str) -> float:
    market_score = float(item.market_fit.score or 0.0) * 100
    if priority_mode == "best_fit":
        return item.rank_score + market_score * 0.25
    if priority_mode == "highest_value":
        value = (
            item.bid_recommendation.recommended_bid
            or item.historical.award_median
            or item.historical.award_max
            or 0
        )
        return min(value / 10000, 250) + market_score * 0.3 + item.rank_score * 0.2
    return item.rank_score * 0.45 + market_score + _decision_bonus(item.label)


def _decision_order(label: str) -> int:
    return {
        "Pursue": 0,
        "Review": 1,
        "Monitor": 2,
        "Skip": 3,
    }.get(label, 2)


def _decision_bonus(label: str) -> int:
    return {
        "Pursue": 40,
        "Review": 24,
        "Monitor": 8,
        "Skip": -100,
    }.get(label, 0)


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * min(1.0, max(0.0, quantile))
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _round_bid_amount(value: float) -> float:
    amount = max(0.0, float(value or 0.0))
    if amount <= 0:
        return 0.0
    if amount < 100000:
        increment = 1000
    elif amount < 1000000:
        increment = 5000
    else:
        increment = 10000
    return float(round(amount / increment) * increment)


def _bid_value_confidence(count: int, basis: str) -> str:
    if count >= 8 and "division" in basis:
        return "Strong"
    if count >= 5:
        return "Moderate"
    if count >= 3:
        return "Directional"
    return "Low"


def _model_value_confidence(mape: float, analog_count: int) -> str:
    if mape <= 0.25 and analog_count >= 6:
        return "Strong"
    if mape <= 0.38 and analog_count >= 4:
        return "Moderate"
    return "Directional"


def _cap_outlier_prediction(predicted: float, fallback: BidRecommendation, profile: BusinessProfile) -> float:
    candidates = [
        value
        for value in (
            fallback.low_bid,
            fallback.high_bid,
            fallback.median_award,
            fallback.average_award,
            profile.max_contract_value * 1.5 if profile.max_contract_value else 0.0,
        )
        if value > 0
    ]
    if not candidates:
        return max(0.0, predicted)
    upper = max(candidates) * 1.35
    lower = min(candidates) * 0.45
    return min(max(predicted, lower), upper)


def _contract_type_label(type_family: str) -> str:
    labels = {
        "rfq": "RFQ/quotation",
        "rft": "tender",
        "tender": "tender",
        "rfp": "proposal",
        "rfsq": "supplier qualification",
    }
    return labels.get(type_family, type_family or "contract type")


def _new_market_context() -> dict[str, Any]:
    return {
        "segment_awards": Counter(),
        "segment_suppliers": defaultdict(Counter),
        "segment_values": defaultdict(list),
        "segment_accessible": Counter(),
        "supplier_awards": Counter(),
        "supplier_profile_fit_awards": Counter(),
        "buyer_awards": Counter(),
    }


def _award_value_context_for_awards(
    profile: BusinessProfile,
    awards: list[AwardRecord],
    today: date,
) -> dict[str, Any]:
    context: dict[str, Any] = {
        "segment_values": defaultdict(list),
        "type_category_values": defaultdict(list),
        "type_values": defaultdict(list),
        "all_fit_values": [],
    }
    seen: set[str] = set()
    for award in sorted(
        awards,
        key=lambda item: (
            item.award_date or date.min,
            item.document_number,
            item.supplier,
            item.award_value,
        ),
    ):
        if award.award_value <= 0:
            continue
        if award.award_date and award.award_date > today:
            continue
        award_key = _market_award_key(award)
        if award_key in seen:
            continue
        seen.add(award_key)
        if _profile_award_fit(profile, award)[0] <= 0:
            continue

        value = float(award.award_value)
        type_family = _type_family(award.solicitation_type)
        category_family = _category_family(award.category)
        segment = _market_segment_key(award)
        context["segment_values"][segment].append(value)
        context["type_category_values"][(category_family, type_family)].append(value)
        context["type_values"][type_family].append(value)
        context["all_fit_values"].append(value)
    return context


def _bid_recommendation_from_model(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    value_features: dict[str, float],
    trained_model: TrainedMarketModel,
    value_context: dict[str, Any],
) -> BidRecommendation:
    fallback = _bid_recommendation_from_context(profile, opportunity, value_context)
    value_model = trained_model.value_model
    value_summary = trained_model.value_summary or {}
    if value_model is None or value_summary.get("status") != "trained":
        fallback.source = "historical_value_fallback"
        return fallback

    predicted = math.expm1(
        float(value_model.predict([[value_features.get(name, 0.0) for name in VALUE_FEATURE_NAMES]])[0])
    )
    rag = opportunity.rag_evidence
    if rag.value_median:
        predicted = predicted * 0.72 + rag.value_median * 0.28
    predicted = _cap_outlier_prediction(predicted, fallback, profile)
    mape = float(value_summary.get("mape") or 0.28)
    uncertainty = max(0.16, min(0.55, mape + (0.06 if len(rag.analogs) < 4 else 0.0)))
    low_bid = _round_bid_amount(predicted * (1.0 - uncertainty))
    high_bid = _round_bid_amount(predicted * (1.0 + uncertainty))
    recommended = _round_bid_amount(predicted)
    evidence = [
        (
            f"Award-value model predicted ${recommended:,.0f} using {value_summary.get('mode', 'trained regression')} "
            f"with holdout MAPE {mape:.1%}."
        ),
    ]
    if rag.analogs:
        evidence.append(
            f"RAG supplied {len(rag.analogs)} analog(s); analog median ${rag.value_median:,.0f}."
        )
    if fallback.evidence:
        evidence.append(f"Baseline fallback: {fallback.evidence[0]}")
    return BidRecommendation(
        source="trained_award_value_model",
        recommended_bid=recommended,
        low_bid=low_bid,
        high_bid=high_bid,
        confidence=_model_value_confidence(mape, len(rag.analogs)),
        contract_type=fallback.contract_type,
        historical_award_count=max(fallback.historical_award_count, len(rag.analogs)),
        average_award=fallback.average_award,
        median_award=fallback.median_award,
        basis="award-value regression plus RAG analog distribution",
        evidence=evidence,
    )


def _bid_recommendation_from_context(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    context: dict[str, Any],
) -> BidRecommendation:
    solicitation = opportunity.solicitation
    type_family = _type_family(solicitation.solicitation_type)
    category_family = _category_family(solicitation.category)
    segment_key = _market_segment_key_from_values(
        solicitation.category,
        solicitation.solicitation_type,
        solicitation.division,
    )
    candidates = [
        ("same category, contract type, and division", context["segment_values"][segment_key]),
        ("same category and contract type", context["type_category_values"][(category_family, type_family)]),
        ("same contract type", context["type_values"][type_family]),
        ("matched profile award history", context["all_fit_values"]),
    ]

    basis = ""
    values: list[float] = []
    for candidate_basis, candidate_values in candidates:
        clean_values = sorted(float(value) for value in candidate_values if float(value) > 0)
        if len(clean_values) >= 3:
            basis = candidate_basis
            values = clean_values
            break

    if not values:
        values = sorted(
            value
            for value in [
                opportunity.historical.award_min,
                opportunity.historical.award_median,
                opportunity.historical.award_max,
            ]
            if value > 0
        )
        basis = "similar award comparison" if values else ""

    if not values:
        return BidRecommendation(
            evidence=["No historical award values were strong enough to suggest a bid amount."],
        )

    average_award = float(mean(values))
    median_award = float(median(values))
    low_bid = _round_bid_amount(_percentile(values, 0.25))
    high_bid = _round_bid_amount(_percentile(values, 0.75))
    if low_bid == high_bid and len(values) > 1:
        low_bid = _round_bid_amount(min(values))
        high_bid = _round_bid_amount(max(values))
    recommended_bid = _round_bid_amount(average_award)
    confidence = _bid_value_confidence(len(values), basis)
    contract_type = _contract_type_label(type_family)
    evidence = [
        (
            f"Bid guidance uses {len(values)} historical {contract_type} award(s) from {basis}; "
            f"average ${average_award:,.0f}, median ${median_award:,.0f}."
        ),
        "Recommended bid is the historical average rounded for a fictional-company demo.",
    ]
    if low_bid and high_bid and low_bid != high_bid:
        evidence.append(f"Suggested range is ${low_bid:,.0f} to ${high_bid:,.0f}.")
    if profile.max_contract_value and recommended_bid > profile.max_contract_value:
        evidence.append(
            f"Recommended amount is above the profile's ${profile.max_contract_value:,.0f} comfort range; review capacity before bidding."
        )

    return BidRecommendation(
        source="historical_contract_type_average",
        recommended_bid=recommended_bid,
        low_bid=low_bid,
        high_bid=high_bid,
        confidence=confidence,
        contract_type=contract_type,
        historical_award_count=len(values),
        average_award=round(average_award, 2),
        median_award=round(median_award, 2),
        basis=basis,
        evidence=evidence,
    )


def _market_context_snapshot(
    profile: BusinessProfile,
    award: AwardRecord,
    context: dict[str, Any],
) -> dict[str, float]:
    return _market_context_snapshot_for_values(
        profile=profile,
        category=award.category,
        solicitation_type=award.solicitation_type,
        division=award.division,
        supplier=award.supplier,
        buyer=_buyer_name(award),
        context=context,
    )


def _market_context_snapshot_for_values(
    profile: BusinessProfile,
    category: str,
    solicitation_type: str,
    division: str,
    supplier: str,
    buyer: str,
    context: dict[str, Any],
) -> dict[str, float]:
    segment = _market_segment_key_from_values(category, solicitation_type, division)
    supplier = _norm(supplier)
    buyer = _norm(buyer)
    segment_awards = int(context["segment_awards"][segment])
    supplier_counts = context["segment_suppliers"][segment]
    segment_values = context["segment_values"][segment]
    top_supplier_share = 0.0
    if segment_awards > 0 and supplier_counts:
        top_supplier_share = max(supplier_counts.values()) / segment_awards
    accessible_value_share = 0.0
    if segment_awards > 0:
        accessible_value_share = context["segment_accessible"][segment] / segment_awards
    median_value_ratio = 0.0
    if segment_values and profile.max_contract_value:
        median_value_ratio = min(5.0, median(segment_values) / profile.max_contract_value)
    return {
        "segment_awards": float(segment_awards),
        "segment_supplier_count": float(len(supplier_counts)),
        "top_supplier_share": float(top_supplier_share),
        "median_value_ratio": float(median_value_ratio),
        "accessible_value_share": float(accessible_value_share),
        "supplier_awards": float(context["supplier_awards"][supplier]),
        "supplier_profile_fit_awards": float(context["supplier_profile_fit_awards"][(profile.profile_id, supplier)]),
        "buyer_awards": float(context["buyer_awards"][buyer]),
    }


def _update_market_context(
    profile: BusinessProfile,
    award: AwardRecord,
    target: int,
    context: dict[str, Any],
) -> None:
    segment = _market_segment_key(award)
    supplier = _norm(award.supplier)
    buyer = _norm(_buyer_name(award))
    context["segment_awards"][segment] += 1
    if supplier:
        context["segment_suppliers"][segment][supplier] += 1
        context["supplier_awards"][supplier] += 1
        if target:
            context["supplier_profile_fit_awards"][(profile.profile_id, supplier)] += 1
    if buyer:
        context["buyer_awards"][buyer] += 1
    if award.award_value > 0:
        context["segment_values"][segment].append(float(award.award_value))
        if award.award_value <= profile.max_contract_value:
            context["segment_accessible"][segment] += 1


def _market_segment_key(award: AwardRecord) -> tuple[str, str, str]:
    return _market_segment_key_from_values(award.category, award.solicitation_type, award.division)


def _market_segment_key_from_values(category: str, solicitation_type: str, division: str) -> tuple[str, str, str]:
    return (
        _category_family(category),
        _type_family(solicitation_type),
        _norm(division),
    )


def _market_award_key(award: AwardRecord) -> str:
    return "|".join(
        [
            _norm(award.document_number),
            _norm(award.supplier),
            f"{award.award_value:.2f}",
        ]
    )


def _type_family(value: str) -> str:
    text = value.lower()
    if "rfq" in text or "quotation" in text:
        return "rfq"
    if "rfsq" in text or "supplier qualification" in text:
        return "rfsq"
    if "rfp" in text or "proposal" in text:
        return "rfp"
    if "tender" in text:
        return "tender"
    return _norm(text)


def _category_family(value: str) -> str:
    text = value.lower()
    if "construction" in text:
        return "construction"
    if "professional" in text or "consulting" in text:
        return "professional"
    if "goods" in text or "supplies" in text or "supply" in text:
        return "goods"
    return _norm(text) or "unknown"


def _buyer_name(award: AwardRecord) -> str:
    for field_name in ("Buyer Name", "buyer_name", "Buyer", "buyer", "Buyer Contact", "buyer_contact"):
        value = award.raw.get(field_name)
        if value:
            return str(value)
    return ""


def _norm(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _stable_bucket(value: str, modulo: int) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % max(1, modulo)
