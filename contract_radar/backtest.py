from __future__ import annotations

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
    false_positive_skips = [item for item in skipped if _looks_like_false_positive(item)]
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

    return {
        "profile": profile.name,
        "evaluated_count": len(evaluated),
        "actionable_count": len(non_skipped),
        "realistic_historical_opportunities": realistic_historical,
        "false_positives_skipped": len(false_positive_skips),
        "capacity_downgrades": len(capacity_downgrades),
        "similar_awards_grounded": similar_awards_grounded,
        "estimated_bid_hours_saved": bid_hours_saved,
        "top_insight": _top_insight(
            profile=profile,
            non_skipped=non_skipped,
            historical_summary=historical_summary,
            false_positive_skips=false_positive_skips,
            bid_hours_saved=bid_hours_saved,
        ),
        "false_positive_examples": [_example(item) for item in false_positive_skips[:3]],
        "capacity_examples": [_example(item) for item in capacity_downgrades[:3]],
    }


def _looks_like_false_positive(item: EvaluatedOpportunity) -> bool:
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


def _top_insight(
    profile: BusinessProfile,
    non_skipped: list[EvaluatedOpportunity],
    historical_summary: dict[str, Any],
    false_positive_skips: list[EvaluatedOpportunity],
    bid_hours_saved: int,
) -> str:
    best = non_skipped[0] if non_skipped else None
    divisions = historical_summary.get("common_divisions") or []
    division = divisions[0].get("name") if divisions and isinstance(divisions[0], dict) else ""
    award_range = historical_summary.get("award_value_range") or {}
    median = award_range.get("median")

    if best and best.historical.similar_count:
        typical = f"${best.historical.award_median:,.0f}" if best.historical.award_median else "an unknown value"
        return (
            f"{profile.name} has a non-obvious revenue signal: {best.solicitation.division or division or 'this buyer'} "
            f"has similar {profile.label.lower()} awards around {typical}, while the engine skipped "
            f"{len(false_positive_skips)} misleading match(es) and saved about {bid_hours_saved} bid-review hour(s)."
        )

    if median:
        return (
            f"Historical Toronto awards show realistic work around ${float(median):,.0f} for this profile; "
            f"the current scan skipped {len(false_positive_skips)} misleading match(es) before owner review."
        )

    return (
        f"The current scan found {len(non_skipped)} actionable item(s), skipped "
        f"{len(false_positive_skips)} misleading match(es), and kept the owner out of low-value bid review."
    )


def _example(item: EvaluatedOpportunity) -> dict[str, Any]:
    return {
        "document_number": item.solicitation.document_number,
        "title": item.solicitation.description,
        "label": item.label,
        "reasons": (item.rejection_reasons or item.reasons)[:3],
        "matched_terms": item.matched_terms[:4],
    }
