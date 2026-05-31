from __future__ import annotations

from datetime import date
from typing import Callable

from contract_radar.history import compare_history, meaningful_terms
from contract_radar.models import (
    AwardRecord,
    BidFitnessTrace,
    BusinessProfile,
    CapacityAssessment,
    EvaluatedOpportunity,
    HistoricalComparison,
    Solicitation,
)


ACCESSIBLE_TYPES = ("rfq", "quotation")
RFSQ_TYPES = ("rfsq", "request for supplier qualification", "supplier qualification")
RFP_TYPES = ("rfp", "request for proposal", "proposal")
TENDER_TYPES = ("rft", "request for tender", "tender")
LARGE_SCOPE_TERMS = {
    "design-build",
    "design build",
    "major construction",
    "construction management",
    "pre-qualified general contractor",
    "full design and construction",
    "new facility construction",
}
URGENCY_WINDOW_DAYS = 5
DECISION_LABELS = ("Pursue", "Review", "Monitor", "Skip")
DEFAULT_PRIORITY_MODE = "best_win_chance"
PRIORITY_MODES = {DEFAULT_PRIORITY_MODE, "best_fit", "highest_value"}
GENERIC_MATCH_TERMS = {
    "preventative maintenance",
    "emergency repair",
    "emergency repairs",
    "mechanical repairs",
    "municipal/public facility service",
    "municipal",
    "public",
}
BROAD_SINGLE_MATCH_TERMS = {
    "administration",
    "management",
    "support",
    "public",
    "municipal",
    "facility",
    "facilities",
}


def evaluate_opportunities(
    profile: BusinessProfile,
    solicitations: list[Solicitation],
    awards: list[AwardRecord],
    today: date,
    priority_mode: str = DEFAULT_PRIORITY_MODE,
    on_evaluated: Callable[[EvaluatedOpportunity, int, int], None] | None = None,
) -> list[EvaluatedOpportunity]:
    priority_mode = normalize_priority_mode(priority_mode)
    evaluated = []
    total = len(solicitations)
    for index, solicitation in enumerate(solicitations, start=1):
        item = _evaluate_one(profile, solicitation, awards, today)
        evaluated.append(item)
        if on_evaluated is not None:
            on_evaluated(item, index, total)
    return sorted(
        evaluated,
        key=lambda item: _sort_key(item, priority_mode, profile),
    )


def normalize_priority_mode(priority_mode: str | None) -> str:
    mode = str(priority_mode or DEFAULT_PRIORITY_MODE).strip().lower()
    return mode if mode in PRIORITY_MODES else DEFAULT_PRIORITY_MODE


def _evaluate_one(
    profile: BusinessProfile,
    solicitation: Solicitation,
    awards: list[AwardRecord],
    today: date,
) -> EvaluatedOpportunity:
    days_until_deadline = (
        (solicitation.submission_deadline - today).days if solicitation.submission_deadline else None
    )
    matched_terms = _matched_profile_terms(profile, solicitation)
    missing = _missing_capabilities(profile, solicitation)
    profile_blockers = set(missing)
    type_complexity = _type_complexity(profile, solicitation)
    text = _solicitation_text(solicitation)

    reasons: list[str] = []
    rejection_reasons: list[str] = []
    rank_score = 0

    if days_until_deadline is not None and days_until_deadline < 0:
        rejection_reasons = ["expired"]
        reasons = ["Submission deadline has passed."]
        historical = HistoricalComparison(
            accessibility="not compared",
            evidence=["Expired opportunity skipped before historical comparison."],
        )
        capacity_assessment = _capacity_assessment(
            profile=profile,
            label="Skip",
            days_until_deadline=days_until_deadline,
            historical=HistoricalComparison(accessibility="not compared"),
            missing=missing,
            type_complexity=type_complexity,
            rejection_reasons=rejection_reasons,
        )
        return EvaluatedOpportunity(
            solicitation=solicitation,
            label="Skip",
            rank_score=0,
            matched_terms=matched_terms,
            missing_requirements=missing,
            reasons=reasons,
            rejection_reasons=rejection_reasons,
            days_until_deadline=days_until_deadline,
            historical=historical,
            capacity_assessment=capacity_assessment,
            bid_fitness_trace=_bid_fitness_trace(
                label="Skip",
                rank_score=0,
                matched_terms=matched_terms,
                missing=missing,
                rejection_reasons=rejection_reasons,
                type_complexity=type_complexity,
                days_until_deadline=days_until_deadline,
                historical=historical,
                capacity_assessment=capacity_assessment,
                reasons=reasons,
            ),
        )

    if matched_terms:
        rank_score += min(len(matched_terms), 8) * 10
        reasons.append(f"Matches {len(matched_terms)} business capability terms.")
    else:
        rejection_reasons = ["wrong service/category"]
        reasons = ["No capability terms matched this business profile."]
        historical = HistoricalComparison(
            accessibility="not compared",
            evidence=["Wrong-fit opportunity skipped before historical comparison."],
        )
        capacity_assessment = _capacity_assessment(
            profile=profile,
            label="Skip",
            days_until_deadline=days_until_deadline,
            historical=HistoricalComparison(accessibility="not compared"),
            missing=missing,
            type_complexity=type_complexity,
            rejection_reasons=rejection_reasons,
        )
        return EvaluatedOpportunity(
            solicitation=solicitation,
            label="Skip",
            rank_score=0,
            matched_terms=[],
            missing_requirements=missing,
            reasons=reasons,
            rejection_reasons=rejection_reasons,
            days_until_deadline=days_until_deadline,
            historical=historical,
            capacity_assessment=capacity_assessment,
            bid_fitness_trace=_bid_fitness_trace(
                label="Skip",
                rank_score=0,
                matched_terms=[],
                missing=missing,
                rejection_reasons=rejection_reasons,
                type_complexity=type_complexity,
                days_until_deadline=days_until_deadline,
                historical=historical,
                capacity_assessment=capacity_assessment,
                reasons=reasons,
            ),
        )

    historical = compare_history(solicitation, awards, profile)

    if _category_or_description_fit(profile, solicitation):
        rank_score += 18
        reasons.append("Category or description aligns with the business profile.")

    if type_complexity == "accessible":
        rank_score += 16
        reasons.append("RFQ/quotation style opportunity is usually easier for a small vendor to pursue.")
    elif type_complexity == "complex":
        rank_score -= 18
        rejection_reasons.append("complex solicitation type")

    if historical.similar_count:
        if historical.award_median <= profile.max_contract_value:
            rank_score += 18
            reasons.append("Similar historical awards were within the preferred contract range.")
        elif (
            historical.award_median <= profile.max_contract_value * 1.25
            and type_complexity == "accessible"
            and len(matched_terms) >= 4
        ):
            rank_score += 10
            reasons.append("Similar awards run slightly above comfort range, but the RFQ is a strong service fit.")
        elif historical.award_median <= profile.max_contract_value * 1.5:
            rank_score -= 6
            missing.append("partner or added capacity")
            reasons.append("Similar awards may be reachable with a partner.")
        else:
            rank_score -= 22
            rejection_reasons.append("historical awards above capacity")

    if days_until_deadline is None:
        rank_score -= 6
        rejection_reasons.append("unclear deadline")
    elif days_until_deadline < URGENCY_WINDOW_DAYS:
        rank_score -= 8
        reasons.append("Deadline is close; owner must act immediately.")
    elif days_until_deadline <= profile.response_days_available:
        rank_score += 6
        reasons.append("Deadline is inside the owner's available response window.")
    else:
        rank_score += 4
        reasons.append("Deadline leaves enough time to prepare.")

    if missing:
        rank_score -= min(len(set(missing)), 4) * 9
        reasons.append("Some requirements exceed the current profile.")
        if profile_blockers:
            rejection_reasons.append("blocked capability mismatch")

    if _contains_any(text, _large_scope_terms(profile)) and matched_terms:
        missing.append("large project delivery capacity")
        rejection_reasons.append("large construction/design-build scope")
        rank_score -= 15

    label = _label(rank_score, matched_terms, missing, rejection_reasons, type_complexity, days_until_deadline)
    capacity_assessment = _capacity_assessment(
        profile=profile,
        label=label,
        days_until_deadline=days_until_deadline,
        historical=historical,
        missing=missing,
        type_complexity=type_complexity,
        rejection_reasons=rejection_reasons,
    )
    label = _apply_capacity_gate(label, capacity_assessment)
    if label == "Skip" and not rejection_reasons:
        rejection_reasons.append("weak evidence")
    if label == "Review" and (type_complexity == "complex" or missing) and "partner or added capacity" not in missing:
        missing.append("partner or added capacity")
    if capacity_assessment.recommended_action == "Pursue After Review":
        reasons.append("Capacity warning requires owner review before pursuing.")
    reasons.extend(
        _supporting_evidence(
            label=label,
            rank_score=rank_score,
            matched_terms=matched_terms,
            missing=missing,
            rejection_reasons=rejection_reasons,
            type_complexity=type_complexity,
            days_until_deadline=days_until_deadline,
            historical=historical,
            capacity_assessment=capacity_assessment,
        )
    )
    bid_fitness_trace = _bid_fitness_trace(
        label=label,
        rank_score=rank_score,
        matched_terms=matched_terms,
        missing=missing,
        rejection_reasons=rejection_reasons,
        type_complexity=type_complexity,
        days_until_deadline=days_until_deadline,
        historical=historical,
        capacity_assessment=capacity_assessment,
        reasons=reasons,
    )

    return EvaluatedOpportunity(
        solicitation=solicitation,
        label=label,
        rank_score=max(0, rank_score),
        matched_terms=sorted(set(matched_terms)),
        missing_requirements=sorted(set(missing)),
        reasons=reasons or ["No strong actionable signal found."],
        rejection_reasons=sorted(set(rejection_reasons)),
        days_until_deadline=days_until_deadline,
        historical=historical,
        capacity_assessment=capacity_assessment,
        bid_fitness_trace=bid_fitness_trace,
    )


def _label(
    rank_score: int,
    matched_terms: list[str],
    missing: list[str],
    rejection_reasons: list[str],
    type_complexity: str,
    days_until_deadline: int | None,
) -> str:
    if "expired" in rejection_reasons:
        return "Skip"
    if not matched_terms:
        return "Skip"
    if "large construction/design-build scope" in rejection_reasons and len(matched_terms) < 3:
        return "Skip"
    if "historical awards above capacity" in rejection_reasons and rank_score < 35:
        return "Skip"
    if "blocked capability mismatch" in rejection_reasons:
        return "Skip"
    if type_complexity == "complex" or missing:
        if rank_score >= 18 and len(matched_terms) >= 2:
            return "Review"
        return "Skip"
    if "unclear deadline" in rejection_reasons:
        return "Monitor" if rank_score >= 25 else "Skip"
    has_specific_match = _has_specific_match(matched_terms)
    if days_until_deadline is not None and 0 <= days_until_deadline < URGENCY_WINDOW_DAYS:
        return "Pursue" if rank_score >= 35 else "Monitor" if rank_score >= 25 else "Skip"
    if rank_score >= 50 and has_specific_match:
        return "Pursue"
    if rank_score >= 25:
        return "Monitor"
    return "Skip"


def _sort_key(item: EvaluatedOpportunity, priority_mode: str, profile: BusinessProfile) -> tuple[object, ...]:
    return (
        item.label == "Skip",
        -_priority_score(item, priority_mode, profile),
        item.days_until_deadline if item.days_until_deadline is not None else 9999,
        item.solicitation.document_number,
    )


def _priority_score(item: EvaluatedOpportunity, priority_mode: str, profile: BusinessProfile) -> float:
    if priority_mode == "best_fit":
        return (
            len(item.matched_terms) * 24
            + item.rank_score * 0.45
            - len(item.missing_requirements) * 14
            + _label_bonus(item.label)
        )
    if priority_mode == "highest_value":
        value = item.historical.award_median or item.historical.award_max or 0
        value_score = min((value / max(profile.max_contract_value, 1.0)) * 100, 220)
        return value_score + item.rank_score * 0.35 - len(item.missing_requirements) * 10 + _label_bonus(item.label)
    return item.rank_score + _label_bonus(item.label)


def _label_bonus(label: str) -> int:
    return {
        "Pursue": 30,
        "Review": 16,
        "Monitor": 4,
        "Skip": -100,
    }.get(label, 0)


def _has_specific_match(matched_terms: list[str]) -> bool:
    normalized = {term.lower().strip() for term in matched_terms}
    generic = {term.lower() for term in GENERIC_MATCH_TERMS}
    return bool(normalized - generic)


def _supporting_evidence(
    label: str,
    rank_score: int,
    matched_terms: list[str],
    missing: list[str],
    rejection_reasons: list[str],
    type_complexity: str,
    days_until_deadline: int | None,
    historical: HistoricalComparison,
    capacity_assessment: CapacityAssessment,
) -> list[str]:
    return [
        f"{label_name}: {label_value}."
        for label_name, label_value in _scorecard_labels(
            label=label,
            rank_score=rank_score,
            matched_terms=matched_terms,
            missing=missing,
            rejection_reasons=rejection_reasons,
            type_complexity=type_complexity,
            days_until_deadline=days_until_deadline,
            historical=historical,
            capacity_assessment=capacity_assessment,
        ).items()
    ]


def _scorecard_labels(
    label: str,
    rank_score: int,
    matched_terms: list[str],
    missing: list[str],
    rejection_reasons: list[str],
    type_complexity: str,
    days_until_deadline: int | None,
    historical: HistoricalComparison,
    capacity_assessment: CapacityAssessment,
) -> dict[str, str]:
    core_fit = "Strong" if len(matched_terms) >= 4 else "Partial" if len(matched_terms) >= 2 else "Weak"
    eligibility = _eligibility_label(label, missing, rejection_reasons, type_complexity)
    effort = _pursuit_effort(type_complexity, missing)
    deadline_risk = _deadline_risk(days_until_deadline)
    competition = _competition_label(historical)
    strategic_value = _strategic_value(rank_score, historical)
    return {
        "Core Fit": core_fit,
        "Eligibility": eligibility,
        "Competition": competition,
        "Pursuit Effort": effort,
        "Deadline Risk": deadline_risk,
        "Strategic Value": strategic_value,
        "Pursuit Load": capacity_assessment.pursuit_load,
        "Response Capacity": capacity_assessment.response_capacity,
        "Execution Capacity": capacity_assessment.execution_capacity,
        "Recommended Action": capacity_assessment.recommended_action,
    }


def _bid_fitness_trace(
    label: str,
    rank_score: int,
    matched_terms: list[str],
    missing: list[str],
    rejection_reasons: list[str],
    type_complexity: str,
    days_until_deadline: int | None,
    historical: HistoricalComparison,
    capacity_assessment: CapacityAssessment,
    reasons: list[str],
) -> BidFitnessTrace:
    matched = sorted(set(matched_terms))
    missing_requirements = sorted(set(missing))
    rejections = sorted(set(rejection_reasons))
    scorecard_labels = _scorecard_labels(
        label=label,
        rank_score=rank_score,
        matched_terms=matched,
        missing=missing_requirements,
        rejection_reasons=rejections,
        type_complexity=type_complexity,
        days_until_deadline=days_until_deadline,
        historical=historical,
        capacity_assessment=capacity_assessment,
    )
    hard_blockers = _trace_hard_blockers(label, missing_requirements, rejections, days_until_deadline)
    soft_warnings = _trace_soft_warnings(
        label=label,
        missing=missing_requirements,
        rejection_reasons=rejections,
        type_complexity=type_complexity,
        days_until_deadline=days_until_deadline,
        capacity_assessment=capacity_assessment,
    )
    positive_signals = _trace_positive_signals(
        matched_terms=matched,
        type_complexity=type_complexity,
        days_until_deadline=days_until_deadline,
        historical=historical,
        capacity_assessment=capacity_assessment,
        reasons=reasons,
    )
    return BidFitnessTrace(
        hard_blockers=hard_blockers,
        soft_warnings=soft_warnings,
        positive_signals=positive_signals,
        requirement_signals=_trace_requirement_signals(matched, missing_requirements, type_complexity, label),
        historical_analogs=_trace_historical_analogs(historical),
        capacity_gates=_trace_capacity_gates(capacity_assessment),
        scorecard_labels=scorecard_labels,
        rules_triggered=_trace_rules_triggered(
            label=label,
            matched_terms=matched,
            rejection_reasons=rejections,
            type_complexity=type_complexity,
            days_until_deadline=days_until_deadline,
            historical=historical,
            capacity_assessment=capacity_assessment,
        ),
        final_rationale=_trace_final_rationale(label, hard_blockers, soft_warnings, positive_signals, scorecard_labels),
    )


def _trace_hard_blockers(
    label: str,
    missing: list[str],
    rejection_reasons: list[str],
    days_until_deadline: int | None,
) -> list[str]:
    if label != "Skip":
        return []

    blockers: list[str] = []
    if "expired" in rejection_reasons:
        blockers.append(f"Submission deadline is closed; {_deadline_phrase(days_until_deadline)}.")
    if "wrong service/category" in rejection_reasons:
        blockers.append("No matching business capability terms were found for this profile.")
    if "blocked capability mismatch" in rejection_reasons:
        blockers.append(_profile_exclusion_message(missing))
    if "historical awards above capacity" in rejection_reasons:
        blockers.append("Similar historical awards appear above the current contract capacity.")
    if "large construction/design-build scope" in rejection_reasons:
        blockers.append("Scope indicates large or design-build delivery outside the current profile.")
    if "unclear deadline" in rejection_reasons:
        blockers.append("Submission deadline is unclear, so bid timing cannot be confirmed.")
    if "complex solicitation type" in rejection_reasons:
        blockers.append("Solicitation format is complex for this profile without owner review.")
    if "weak evidence" in rejection_reasons:
        blockers.append("Fit evidence is too weak to recommend a bid.")

    if not blockers:
        blockers.append("Decision is Skip because the available evidence does not support a viable bid.")
    return _unique_messages(blockers)


def _trace_soft_warnings(
    label: str,
    missing: list[str],
    rejection_reasons: list[str],
    type_complexity: str,
    days_until_deadline: int | None,
    capacity_assessment: CapacityAssessment,
) -> list[str]:
    warnings = [
        warning
        for warning in capacity_assessment.warnings
        if not (
            days_until_deadline is not None
            and days_until_deadline < 0
            and warning.startswith("Response Capacity:")
        )
    ]
    if label != "Skip" and days_until_deadline is None:
        warnings.append("Deadline: unclear deadline; confirm bid timing before committing.")
    elif label != "Skip" and days_until_deadline is not None and 0 <= days_until_deadline < URGENCY_WINDOW_DAYS:
        warnings.append(f"Deadline: urgent response window; {_deadline_phrase(days_until_deadline)}.")

    if label != "Skip" and type_complexity == "complex":
        warnings.append("Solicitation Type: complex format; confirm proposal effort and prerequisites.")
    if label != "Skip" and missing:
        warnings.append(f"Requirement Review: confirm {', '.join(missing[:3])}.")
    if label != "Skip" and "historical awards above capacity" in rejection_reasons:
        warnings.append("Historical Size: similar awards may exceed the current comfort range.")
    if capacity_assessment.recommended_action == "Pursue After Review":
        warnings.append("Capacity Gate: owner review required before committing pursuit resources.")
    return _unique_messages(warnings)


def _trace_positive_signals(
    matched_terms: list[str],
    type_complexity: str,
    days_until_deadline: int | None,
    historical: HistoricalComparison,
    capacity_assessment: CapacityAssessment,
    reasons: list[str],
) -> list[str]:
    signals: list[str] = []
    if matched_terms:
        signals.append(f"Capability fit: {', '.join(matched_terms[:5])}.")
    if _has_specific_match(matched_terms):
        signals.append("Specific capability terms matched beyond generic municipal language.")
    if type_complexity == "accessible":
        signals.append("RFQ/quotation format is usually easier for a small vendor to pursue.")
    elif type_complexity == "standard":
        signals.append("Solicitation format is standard for this profile.")
    if historical.similar_count:
        signals.append(f"Historical comparison found similar awards: {historical.accessibility}.")
    if "accessible" in historical.accessibility.lower():
        signals.append("Similar historical awards look accessible for this business size.")
    if capacity_assessment.recommended_action == "Pursue Now":
        signals.append("Capacity gates support immediate pursuit.")
    if days_until_deadline is not None and days_until_deadline >= URGENCY_WINDOW_DAYS:
        signals.append(f"Deadline leaves a workable response window; {_deadline_phrase(days_until_deadline)}.")

    for reason in reasons:
        if _is_trace_positive_reason(reason):
            signals.append(reason)
    return _unique_messages(signals)


def _trace_requirement_signals(
    matched_terms: list[str],
    missing: list[str],
    type_complexity: str,
    label: str,
) -> list[str]:
    signals: list[str] = []
    signals.extend(f"Matched capability: {term}." for term in matched_terms[:6])
    if missing:
        prefix = "Profile exclusion" if label == "Skip" else "Needs review or partner"
        signals.extend(f"{prefix}: {requirement}." for requirement in missing[:6])
    elif matched_terms:
        signals.append("No missing profile capability was triggered by the description.")
    if type_complexity == "accessible":
        signals.append("Procurement format signal: accessible RFQ/quotation.")
    elif type_complexity == "complex":
        signals.append("Procurement format signal: complex proposal or qualification process.")
    else:
        signals.append("Procurement format signal: standard solicitation.")
    return _unique_messages(signals)


def _trace_historical_analogs(historical: HistoricalComparison) -> list[str]:
    analogs = list(historical.evidence[:5])
    if historical.accessibility:
        analogs.append(f"Historical accessibility: {historical.accessibility}.")
    if not analogs:
        analogs.append("Historical comparison was not available.")
    return _unique_messages(analogs)


def _trace_capacity_gates(capacity_assessment: CapacityAssessment) -> list[str]:
    return _unique_messages(
        [
            f"Pursuit Load: {capacity_assessment.pursuit_load}.",
            f"Response Capacity: {capacity_assessment.response_capacity}.",
            f"Execution Capacity: {capacity_assessment.execution_capacity}.",
            f"Recommended Action: {capacity_assessment.recommended_action}.",
        ]
    )


def _trace_rules_triggered(
    label: str,
    matched_terms: list[str],
    rejection_reasons: list[str],
    type_complexity: str,
    days_until_deadline: int | None,
    historical: HistoricalComparison,
    capacity_assessment: CapacityAssessment,
) -> list[str]:
    rules: list[str] = []
    rules.append("Capability match rule" if matched_terms else "No capability match rule")
    if matched_terms and not _has_specific_match(matched_terms):
        rules.append("Generic-match guard rule")
    if type_complexity == "accessible":
        rules.append("Accessible RFQ/quotation rule")
    elif type_complexity == "complex":
        rules.append("Complex solicitation type rule")
    else:
        rules.append("Standard solicitation type rule")

    if days_until_deadline is None:
        rules.append("Deadline rule: unclear")
    elif days_until_deadline < 0:
        rules.append("Deadline rule: expired")
    elif days_until_deadline < URGENCY_WINDOW_DAYS:
        rules.append("Deadline rule: urgent")
    else:
        rules.append("Deadline rule: workable")

    if historical.similar_count:
        if "accessible" in historical.accessibility.lower():
            rules.append("Historical analog rule: accessible")
        elif "larger" in historical.accessibility.lower():
            rules.append("Historical analog rule: above capacity")
        else:
            rules.append("Historical analog rule: review")
    else:
        rules.append("Historical analog rule: insufficient history")

    rejection_rule_labels = {
        "blocked capability mismatch": "False-positive blocker: blocked capability mismatch",
        "wrong service/category": "False-positive blocker: wrong service/category",
        "large construction/design-build scope": "Large/design-build scope rule",
        "historical awards above capacity": "Historical capacity blocker rule",
        "complex solicitation type": "Complex procurement review rule",
        "unclear deadline": "Unclear deadline review rule",
        "expired": "Expired opportunity blocker rule",
        "weak evidence": "Weak-evidence decision rule",
    }
    rules.extend(rejection_rule_labels[reason] for reason in rejection_reasons if reason in rejection_rule_labels)

    if capacity_assessment.recommended_action == "Pursue After Review":
        rules.append("Capacity gate: pursue after review")
    elif capacity_assessment.recommended_action == "Pursue Now":
        rules.append("Capacity gate: pursue now")
    elif capacity_assessment.recommended_action.startswith("Skip"):
        rules.append("Capacity gate: skip")
    else:
        rules.append("Capacity gate: monitor")

    rules.append(f"Final decision rule: {label}")
    return _unique_messages(rules)


def _trace_final_rationale(
    label: str,
    hard_blockers: list[str],
    soft_warnings: list[str],
    positive_signals: list[str],
    scorecard_labels: dict[str, str],
) -> str:
    if hard_blockers:
        return f"{label}: {_clean_sentence(hard_blockers[0])}."
    if label == "Pursue":
        signal = _clean_sentence(positive_signals[0]) if positive_signals else "fit and capacity signals are favorable"
        action = scorecard_labels.get("Recommended Action", "Pursue Now")
        return f"Pursue: {signal}. Recommended action is {action}."
    if label == "Review":
        warning = _clean_sentence(soft_warnings[0]) if soft_warnings else "owner review is needed before committing"
        signal = _clean_sentence(positive_signals[0]) if positive_signals else "there is partial fit evidence"
        return f"Review: {warning}. Main upside is {signal}."
    if label == "Monitor":
        signal = _clean_sentence(positive_signals[0]) if positive_signals else "fit evidence is not strong enough yet"
        return f"Monitor: {signal}; watch for clearer eligibility or timing."
    return "Skip: available evidence does not support a bid."


def _profile_exclusion_message(missing: list[str]) -> str:
    if not missing:
        return "A profile exclusion was triggered by the solicitation scope."
    return f"Required scope conflicts with profile exclusions: {', '.join(missing[:4])}."


def _deadline_phrase(days_until_deadline: int | None) -> str:
    if days_until_deadline is None:
        return "deadline is unclear"
    if days_until_deadline < 0:
        return f"deadline passed {abs(days_until_deadline)} day(s) ago"
    if days_until_deadline == 0:
        return "deadline is today"
    if days_until_deadline == 1:
        return "1 day remains"
    return f"{days_until_deadline} days remain"


def _is_trace_positive_reason(reason: str) -> bool:
    positive_prefixes = (
        "Matches ",
        "Category or description aligns",
        "RFQ/quotation style",
        "Similar historical awards were within",
        "Similar awards run slightly above",
        "Deadline is inside",
        "Deadline leaves enough",
    )
    blocked_prefixes = (
        "Core Fit:",
        "Eligibility:",
        "Competition:",
        "Pursuit Effort:",
        "Deadline Risk:",
        "Strategic Value:",
        "Pursuit Load:",
        "Response Capacity:",
        "Execution Capacity:",
        "Recommended Action:",
        "Some requirements",
        "Capacity warning",
        "Deadline is close",
    )
    return reason.startswith(positive_prefixes) and not reason.startswith(blocked_prefixes)


def _clean_sentence(value: str) -> str:
    return value.strip().rstrip(".")


def _unique_messages(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        clean = value.strip()
        key = clean.lower()
        if clean and key not in seen:
            seen.add(key)
            unique.append(clean)
    return unique


def _capacity_assessment(
    profile: BusinessProfile,
    label: str,
    days_until_deadline: int | None,
    historical: HistoricalComparison,
    missing: list[str],
    type_complexity: str,
    rejection_reasons: list[str],
) -> CapacityAssessment:
    pursuit_load = _pursuit_load_label(profile)
    response_capacity = _response_capacity_label(days_until_deadline)
    execution_capacity = _execution_capacity_label(
        profile=profile,
        historical=historical,
        missing=missing,
        type_complexity=type_complexity,
        rejection_reasons=rejection_reasons,
    )
    recommended_action = _capacity_recommended_action(
        label=label,
        pursuit_load=pursuit_load,
        response_capacity=response_capacity,
        execution_capacity=execution_capacity,
    )
    return CapacityAssessment(
        pursuit_load=pursuit_load,
        response_capacity=response_capacity,
        execution_capacity=execution_capacity,
        recommended_action=recommended_action,
        warnings=_capacity_warnings(
            profile=profile,
            pursuit_load=pursuit_load,
            response_capacity=response_capacity,
            execution_capacity=execution_capacity,
            days_until_deadline=days_until_deadline,
            historical=historical,
        ),
    )


def _apply_capacity_gate(label: str, assessment: CapacityAssessment) -> str:
    if label == "Pursue" and assessment.recommended_action == "Pursue After Review":
        return "Review"
    return label


def _pursuit_load_label(profile: BusinessProfile) -> str:
    max_active = max(1, profile.max_active_pursuits)
    active = max(0, profile.active_pursuit_count)
    if active >= max_active:
        return "Overloaded"
    if active >= max_active - 1 or active / max_active >= 0.67:
        return "Busy"
    return "Clear"


def _response_capacity_label(days_until_deadline: int | None) -> str:
    if days_until_deadline is None:
        return "Tight"
    if days_until_deadline < URGENCY_WINDOW_DAYS:
        return "At Risk"
    if days_until_deadline <= 10:
        return "Tight"
    return "Enough Time"


def _execution_capacity_label(
    profile: BusinessProfile,
    historical: HistoricalComparison,
    missing: list[str],
    type_complexity: str,
    rejection_reasons: list[str],
) -> str:
    if (
        "large construction/design-build scope" in rejection_reasons
        or "historical awards above capacity" in rejection_reasons
        or historical.award_median > profile.max_contract_value * 1.5
    ):
        return "Likely Too Large"
    if (
        historical.award_median > profile.max_contract_value
        or type_complexity == "complex"
        or any("capacity" in item.lower() or "partner" in item.lower() for item in missing)
    ):
        return "Needs Scheduling Review"
    return "Fits Team"


def _capacity_recommended_action(
    label: str,
    pursuit_load: str,
    response_capacity: str,
    execution_capacity: str,
) -> str:
    if label == "Skip":
        return "Skip For Capacity" if execution_capacity == "Likely Too Large" else "Skip"
    if label == "Monitor":
        return "Monitor"
    if label == "Review":
        return "Pursue After Review"
    if label == "Pursue":
        risk_pair = response_capacity in {"Tight", "At Risk"} or execution_capacity != "Fits Team"
        if pursuit_load == "Overloaded" and risk_pair:
            return "Pursue After Review"
        if execution_capacity == "Likely Too Large":
            return "Pursue After Review"
        return "Pursue Now"
    return "Monitor"


def _capacity_warnings(
    profile: BusinessProfile,
    pursuit_load: str,
    response_capacity: str,
    execution_capacity: str,
    days_until_deadline: int | None,
    historical: HistoricalComparison,
) -> list[str]:
    warnings: list[str] = []
    if pursuit_load == "Overloaded":
        warnings.append(
            f"Pursuit Load: Overloaded - {profile.active_pursuit_count} active bid(s) already at the limit of {profile.max_active_pursuits}."
        )
    elif pursuit_load == "Busy":
        warnings.append(
            f"Pursuit Load: Busy - {profile.active_pursuit_count} active bid(s) already in progress."
        )
    if response_capacity == "At Risk":
        if days_until_deadline is None:
            warnings.append("Response Capacity: At Risk - deadline is unclear.")
        else:
            warnings.append(f"Response Capacity: At Risk - only {days_until_deadline} day(s) remain.")
    elif response_capacity == "Tight":
        warnings.append("Response Capacity: Tight - owner should confirm bid-writing time before pursuing.")
    if execution_capacity == "Needs Scheduling Review":
        warnings.append("Execution Capacity: Needs Scheduling Review - confirm staff and site coverage.")
    elif execution_capacity == "Likely Too Large":
        value = historical.award_median or historical.award_max
        if value:
            warnings.append(f"Execution Capacity: Likely Too Large - similar awards run around ${value:,.0f}.")
        else:
            warnings.append("Execution Capacity: Likely Too Large - scope exceeds the current profile.")
    return warnings


def _eligibility_label(
    label: str,
    missing: list[str],
    rejection_reasons: list[str],
    type_complexity: str,
) -> str:
    if label == "Skip" and ("expired" in rejection_reasons or "wrong service/category" in rejection_reasons):
        return "Blocked"
    if missing or type_complexity == "complex" or "unclear deadline" in rejection_reasons:
        return "Needs Review"
    return "Clear"


def _pursuit_effort(type_complexity: str, missing: list[str]) -> str:
    if type_complexity == "complex" or len(set(missing)) >= 2:
        return "High"
    if missing:
        return "Medium"
    return "Low"


def _deadline_risk(days_until_deadline: int | None) -> str:
    if days_until_deadline is None:
        return "Tight"
    if days_until_deadline < 0:
        return "Critical"
    if days_until_deadline < URGENCY_WINDOW_DAYS:
        return "Critical"
    if days_until_deadline <= 10:
        return "Tight"
    return "Manageable"


def _competition_label(historical: HistoricalComparison) -> str:
    if not historical.similar_count:
        return "Unknown"
    if "accessible" in historical.accessibility.lower():
        return "Moderate"
    return "High"


def _strategic_value(rank_score: int, historical: HistoricalComparison) -> str:
    if rank_score >= 52 or historical.award_median >= 100000:
        return "High"
    if rank_score >= 30 or historical.similar_count:
        return "Medium"
    return "Low"


def _matched_profile_terms(profile: BusinessProfile, solicitation: Solicitation) -> list[str]:
    text_terms = meaningful_terms(_solicitation_text(solicitation))
    text_lower = _solicitation_text(solicitation).lower()
    matched: list[str] = []
    for skill in profile.skills + [profile.business_type]:
        skill_terms = meaningful_terms(skill)
        if not skill_terms:
            continue
        if len(skill_terms) == 1 and next(iter(skill_terms)) in BROAD_SINGLE_MATCH_TERMS:
            continue
        overlap = skill_terms & text_terms
        required_overlap = 1 if len(skill_terms) == 1 else 2
        if skill.lower() in text_lower or len(overlap) >= required_overlap:
            matched.append(skill)
    return matched


def _missing_capabilities(profile: BusinessProfile, solicitation: Solicitation) -> list[str]:
    text = _solicitation_text(solicitation).lower()
    missing = []
    for capability in profile.missing_capabilities:
        capability_text = capability.lower()
        capability_terms = meaningful_terms(capability_text)
        if capability_text in text or len(capability_terms & meaningful_terms(text)) >= 2:
            missing.append(capability)
    return missing


def _category_or_description_fit(profile: BusinessProfile, solicitation: Solicitation) -> bool:
    profile_terms = meaningful_terms(" ".join([profile.business_type, *profile.skills]))
    solicitation_terms = meaningful_terms(_solicitation_text(solicitation))
    return len(profile_terms & solicitation_terms) >= 2


def _type_complexity(profile: BusinessProfile, solicitation: Solicitation) -> str:
    text = " ".join([solicitation.solicitation_type, solicitation.description, solicitation.category]).lower()
    if _contains_any(text, ACCESSIBLE_TYPES):
        return "accessible"
    if _contains_any(text, RFSQ_TYPES):
        return "complex"
    if _contains_any(text, RFP_TYPES):
        if profile.profile_id == "professional_engineering_design":
            return "standard"
        return "complex"
    if _contains_any(text, TENDER_TYPES):
        if profile.profile_id in {"road_civil_infrastructure", "parks_landscape"}:
            return "standard"
        return "complex"
    if _contains_any(text, _large_scope_terms(profile)):
        return "complex"
    return "standard"


def _large_scope_terms(profile: BusinessProfile) -> set[str]:
    if profile.profile_id == "road_civil_infrastructure":
        return {
            "design-build",
            "design build",
            "professional consulting engineering",
            "architectural design",
            "design-only",
        }
    if profile.profile_id == "parks_landscape":
        return {
            "major road construction",
            "watermain replacement",
            "sewer rehabilitation",
            "design-build",
            "design build",
        }
    if profile.profile_id == "professional_engineering_design":
        return {
            "construction services",
            "general contractor",
            "road paving",
            "supply and custom application",
            "construction-only",
        }
    return LARGE_SCOPE_TERMS


def _contains_any(text: str, terms: set[str] | tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _solicitation_text(solicitation: Solicitation) -> str:
    return " ".join(
        [
            solicitation.solicitation_type,
            solicitation.category,
            solicitation.description,
            solicitation.division,
        ]
    )
