from __future__ import annotations

import math
import hashlib
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from statistics import median
from typing import Any

from contract_radar.backtest import looks_like_false_positive
from contract_radar.history import _profile_award_fit, meaningful_terms
from contract_radar.matcher import evaluate_opportunities
from contract_radar.models import AwardRecord, BusinessProfile, EvaluatedOpportunity, MarketFitSignal, Solicitation


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
    return TrainedMarketModel(profile_id=profile.profile_id, model=model, summary=summary)


def apply_market_intelligence(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
    awards: list[AwardRecord],
    trained_model: TrainedMarketModel,
    today: date,
    priority_mode: str = "best_win_chance",
) -> list[EvaluatedOpportunity]:
    context = _market_context_for_awards(profile, awards, today)
    model = trained_model.model
    for opportunity in opportunities:
        features = extract_market_opportunity_features(profile, opportunity, context)
        score = float(model.predict_proba([[features.get(name, 0.0) for name in MARKET_FEATURE_NAMES]])[0][1])
        signal = _market_signal_from_score(opportunity, features, score, trained_model)
        opportunity.market_fit = signal
        _attach_market_signal_to_trace(opportunity, signal)

    return sorted(
        opportunities,
        key=lambda item: _market_sort_key(item, priority_mode),
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


def feature_matrix(examples: list[RankerExample]) -> list[list[float]]:
    return [[example.features.get(name, 0.0) for name in FEATURE_NAMES] for example in examples]


def market_feature_matrix(examples: list[MarketExample]) -> list[list[float]]:
    return [[example.features.get(name, 0.0) for name in MARKET_FEATURE_NAMES] for example in examples]


def target_vector(examples: list[RankerExample]) -> list[int]:
    return [example.target for example in examples]


def market_target_vector(examples: list[MarketExample]) -> list[int]:
    return [example.target for example in examples]


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
        value = item.historical.award_median or item.historical.award_max or 0
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
