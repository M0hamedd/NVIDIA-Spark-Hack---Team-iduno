from __future__ import annotations

from collections import Counter
from typing import Any

from contract_radar.models import BusinessProfile, EvaluatedOpportunity


BID_HOURS_PER_SKIPPED_OPPORTUNITY = 2


def scorecard_from_evaluated(
    profile: BusinessProfile,
    evaluated: list[EvaluatedOpportunity],
    historical_summary: dict[str, Any],
) -> dict[str, Any]:
    non_skipped = [item for item in evaluated if item.label != "Skip"]
    skipped = [item for item in evaluated if item.label == "Skip"]
    false_positive_skips = [item for item in skipped if looks_like_false_positive(item)]
    capacity_downgrades = [
        item
        for item in evaluated
        if item.label == "Review"
        and item.capacity_assessment.recommended_action == "Pursue After Review"
    ]
    similar_awards_grounded = sum(
        item.historical.similar_count for item in non_skipped if item.historical.similar_count
    )
    realistic_historical = int(historical_summary.get("realistic_count") or 0)
    bid_hours_saved = len(skipped) * BID_HOURS_PER_SKIPPED_OPPORTUNITY
    best = non_skipped[0] if non_skipped else None
    buyer_division_pattern = _buyer_division_pattern(best, historical_summary)
    similar_award_range = _award_band(best, historical_summary)

    return {
        "profile": profile.name,
        "evaluated_count": len(evaluated),
        "actionable_count": len(non_skipped),
        "realistic_historical_opportunities": realistic_historical,
        "false_positives_skipped": len(false_positive_skips),
        "capacity_downgrades": len(capacity_downgrades),
        "similar_awards_grounded": similar_awards_grounded,
        "estimated_bid_hours_saved": bid_hours_saved,
        "best_current_opportunity": _opportunity_summary(best, historical_summary),
        "buyer_division_pattern": buyer_division_pattern,
        "similar_award_range": similar_award_range,
        "similar_award_examples": _similar_award_examples(best, historical_summary),
        "false_positive_categories": _false_positive_categories(false_positive_skips),
        "capacity_downgrade_reasons": _capacity_downgrade_reasons(capacity_downgrades),
        "top_insight": _top_insight(
            profile=profile,
            non_skipped=non_skipped,
            historical_summary=historical_summary,
            false_positive_skips=false_positive_skips,
            bid_hours_saved=bid_hours_saved,
        ),
        "false_positive_examples": [_example(item) for item in false_positive_skips[:3]],
        "capacity_examples": [_capacity_example(item) for item in capacity_downgrades[:3]],
    }


def looks_like_false_positive(item: EvaluatedOpportunity) -> bool:
    blockers = " ".join(
        [
            *item.rejection_reasons,
            *item.missing_requirements,
            item.solicitation.description,
            item.solicitation.category,
        ]
    ).lower()
    false_positive_terms = (
        "maintenance",
        "repair",
        "software",
        "road",
        "paving",
        "landscaping",
        "food",
        "kitchen",
        "legal",
        "design-build",
        "construction",
    )
    has_generic_overlap = bool(item.matched_terms) or any(term in blockers for term in false_positive_terms)
    has_blocker = bool(item.rejection_reasons or item.missing_requirements)
    return has_generic_overlap and has_blocker


def _looks_like_false_positive(item: EvaluatedOpportunity) -> bool:
    return looks_like_false_positive(item)


def _top_insight(
    profile: BusinessProfile,
    non_skipped: list[EvaluatedOpportunity],
    historical_summary: dict[str, Any],
    false_positive_skips: list[EvaluatedOpportunity],
    bid_hours_saved: int,
) -> str:
    best = non_skipped[0] if non_skipped else None
    buyer_division_pattern = _buyer_division_pattern(best, historical_summary)
    award_band = _award_band(best, historical_summary)
    false_positive_category = _false_positive_category(false_positive_skips)
    false_positive_phrase = (
        f"{len(false_positive_skips)} false-positive match(es), including {false_positive_category}"
        if false_positive_category
        else f"{len(false_positive_skips)} false-positive match(es)"
    )

    if best and best.historical.similar_count:
        return (
            f"{profile.name} has a data-backed bid signal on {best.solicitation.document_number}: "
            f"{buyer_division_pattern} matches {award_band}. Action: prioritize owner review for this "
            f"{best.label.lower()} opportunity while filtering {false_positive_phrase}, preserving about "
            f"{bid_hours_saved} bid-review hour(s) for higher-probability work."
        )

    if award_band != "an unknown award band":
        return (
            f"Historical Toronto awards show {award_band} through {buyer_division_pattern}. Action: use the "
            f"engine shortlist first because it filtered {false_positive_phrase}, saving about "
            f"{bid_hours_saved} bid-review hour(s) before owner review."
        )

    return (
        f"The current scan found {len(non_skipped)} actionable item(s), skipped "
        f"{false_positive_phrase}, and kept the owner out of low-value bid review."
    )


def _buyer_division_pattern(
    best: EvaluatedOpportunity | None,
    historical_summary: dict[str, Any],
) -> str:
    divisions = historical_summary.get("common_divisions") or []
    buyers = historical_summary.get("common_buyers") or []
    top_division = divisions[0] if divisions and isinstance(divisions[0], dict) else {}
    top_buyer = buyers[0] if buyers and isinstance(buyers[0], dict) else {}
    historical_division = str(top_division.get("name") or "").strip()
    historical_division_count = int(top_division.get("count") or 0)
    historical_buyer = str(top_buyer.get("name") or "").strip()
    historical_buyer_count = int(top_buyer.get("count") or 0)
    current_buyer = (best.solicitation.buyer_name if best else "").strip()
    current_division = (best.solicitation.division if best else "").strip()

    if historical_buyer and historical_division:
        return (
            f"historical buyer/division pattern {historical_buyer} / {historical_division} "
            f"({historical_buyer_count or historical_division_count} realistic award(s))"
        )
    if current_buyer and historical_division:
        return (
            f"buyer {current_buyer} in {current_division or historical_division}, aligned with the "
            f"historical {historical_division} division pattern ({historical_division_count} realistic award(s))"
        )
    if current_division and historical_division:
        return (
            f"division {current_division}, aligned with the historical {historical_division} pattern "
            f"({historical_division_count} realistic award(s))"
        )
    if historical_division:
        return f"historical division pattern {historical_division} ({historical_division_count} realistic award(s))"
    if current_buyer or current_division:
        return f"current buyer/division {current_buyer or 'unknown buyer'} / {current_division or 'unknown division'}"
    return "the evaluated buyer/division pattern"


def _award_band(best: EvaluatedOpportunity | None, historical_summary: dict[str, Any]) -> str:
    award_range = historical_summary.get("award_value_range") or {}
    minimum = _float_or_none(award_range.get("min"))
    median = _float_or_none(award_range.get("median"))
    maximum = _float_or_none(award_range.get("max"))
    if minimum and maximum:
        if median:
            return f"historical award band {_money(minimum)}-{_money(maximum)} (median {_money(median)})"
        return f"historical award band {_money(minimum)}-{_money(maximum)}"
    if best and best.historical.award_min and best.historical.award_max:
        if best.historical.award_median:
            return (
                f"similar-award band {_money(best.historical.award_min)}-{_money(best.historical.award_max)} "
                f"(median {_money(best.historical.award_median)})"
            )
        return f"similar-award band {_money(best.historical.award_min)}-{_money(best.historical.award_max)}"
    return "an unknown award band"


def _false_positive_category(false_positive_skips: list[EvaluatedOpportunity]) -> str:
    if not false_positive_skips:
        return ""
    pairs = Counter((_category(item), _primary_blocker(item)) for item in false_positive_skips)
    category, blocker = pairs.most_common(1)[0][0]
    if category and blocker:
        return f"{category}/{blocker}"
    return category or blocker


def _opportunity_summary(
    item: EvaluatedOpportunity | None,
    historical_summary: dict[str, Any],
) -> dict[str, Any]:
    if item is None:
        return {}
    solicitation = item.solicitation
    return {
        "document_number": solicitation.document_number,
        "title": solicitation.description,
        "label": item.label,
        "buyer": solicitation.buyer_name,
        "division": solicitation.division,
        "deadline": solicitation.submission_deadline.isoformat() if solicitation.submission_deadline else None,
        "rank_score": item.rank_score,
        "matched_terms": item.matched_terms[:5],
        "decision_reason": item.bid_fitness_trace.final_rationale or (item.reasons[0] if item.reasons else ""),
        "award_range": _award_band(item, historical_summary),
        "similar_awards": _similar_award_examples(item, historical_summary),
        "capacity_warnings": item.capacity_assessment.warnings[:3],
        "recommended_action": item.capacity_assessment.recommended_action,
    }


def _similar_award_examples(
    best: EvaluatedOpportunity | None,
    historical_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    realistic_max = _historical_award_max(historical_summary)
    if best and best.historical.examples:
        current_examples = _normal_award_examples(best.historical.examples, max_award_value=realistic_max)
        if current_examples:
            return current_examples
    sample_awards = historical_summary.get("sample_awards") or []
    return _normal_award_examples(sample_awards)


def _normal_award_examples(
    raw_examples: Any,
    max_award_value: float | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(raw_examples, list):
        return []
    examples: list[dict[str, Any]] = []
    for raw in raw_examples:
        if not isinstance(raw, dict):
            continue
        value = _float_or_none(raw.get("award_value")) or 0.0
        if max_award_value is not None and value > max_award_value:
            continue
        examples.append(
            {
                "document_number": str(raw.get("document_number") or "").strip(),
                "description": str(raw.get("description") or "").strip(),
                "division": str(raw.get("division") or "").strip(),
                "buyer": str(raw.get("buyer") or "").strip(),
                "supplier": str(raw.get("supplier") or "").strip(),
                "award_value": value,
                "award_value_label": _money(value) if value else "",
                "award_date": raw.get("award_date"),
                "matched_terms": _clean_terms(raw.get("matched_terms")),
            }
        )
        if len(examples) >= 3:
            break
    return examples


def _historical_award_max(historical_summary: dict[str, Any]) -> float | None:
    award_range = historical_summary.get("award_value_range") or {}
    return _float_or_none(award_range.get("max"))


def _clean_terms(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(term) for term in value[:5] if str(term).strip()]


def _false_positive_categories(false_positive_skips: list[EvaluatedOpportunity]) -> list[dict[str, Any]]:
    if not false_positive_skips:
        return []
    pairs = Counter((_category(item), _primary_blocker(item)) for item in false_positive_skips)
    examples_by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in false_positive_skips:
        pair = (_category(item), _primary_blocker(item))
        examples_by_pair.setdefault(pair, [])
        if len(examples_by_pair[pair]) < 2:
            examples_by_pair[pair].append(_example(item))

    categories: list[dict[str, Any]] = []
    for (category, blocker), count in pairs.most_common(5):
        categories.append(
            {
                "category": category or "Uncategorized",
                "blocker": blocker or "weak evidence",
                "count": count,
                "examples": examples_by_pair.get((category, blocker), []),
            }
        )
    return categories


def _capacity_downgrade_reasons(capacity_downgrades: list[EvaluatedOpportunity]) -> list[dict[str, Any]]:
    if not capacity_downgrades:
        return []
    reasons = Counter(_capacity_reason(item) for item in capacity_downgrades)
    return [
        {"reason": reason, "count": count}
        for reason, count in reasons.most_common(5)
    ]


def _capacity_reason(item: EvaluatedOpportunity) -> str:
    if item.capacity_assessment.warnings:
        return item.capacity_assessment.warnings[0]
    if item.missing_requirements:
        return f"Needs review: {item.missing_requirements[0]}"
    return item.capacity_assessment.recommended_action or "Owner review required before pursuit"


def _category(item: EvaluatedOpportunity) -> str:
    return item.solicitation.category.strip()


def _primary_blocker(item: EvaluatedOpportunity) -> str:
    for blocker in [*item.missing_requirements, *item.rejection_reasons]:
        if blocker and blocker not in {"wrong service/category", "weak evidence"}:
            return blocker
    return ""


def _float_or_none(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric > 0 else None


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _example(item: EvaluatedOpportunity) -> dict[str, Any]:
    return {
        "document_number": item.solicitation.document_number,
        "title": item.solicitation.description,
        "label": item.label,
        "category": item.solicitation.category,
        "division": item.solicitation.division,
        "buyer": item.solicitation.buyer_name,
        "deadline": item.solicitation.submission_deadline.isoformat() if item.solicitation.submission_deadline else None,
        "primary_blocker": _primary_blocker(item),
        "reasons": (item.rejection_reasons or item.reasons)[:3],
        "matched_terms": item.matched_terms[:4],
    }


def _capacity_example(item: EvaluatedOpportunity) -> dict[str, Any]:
    example = _example(item)
    example.update(
        {
            "recommended_action": item.capacity_assessment.recommended_action,
            "capacity_warnings": item.capacity_assessment.warnings[:3],
            "award_range": _item_award_range(item),
        }
    )
    return example


def _item_award_range(item: EvaluatedOpportunity) -> str:
    historical = item.historical
    if historical.award_min and historical.award_max:
        if historical.award_median:
            return f"{_money(historical.award_min)}-{_money(historical.award_max)} (median {_money(historical.award_median)})"
        return f"{_money(historical.award_min)}-{_money(historical.award_max)}"
    return ""
