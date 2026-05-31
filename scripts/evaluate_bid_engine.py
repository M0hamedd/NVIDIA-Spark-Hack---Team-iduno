from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from contract_radar import config
from contract_radar.backtest import (
    BID_HOURS_PER_SKIPPED_OPPORTUNITY,
    looks_like_false_positive,
    scorecard_from_evaluated,
)
from contract_radar.data import ProcurementDataUnavailable, load_procurement_data
from contract_radar.history import meaningful_terms, summarize_past_opportunities
from contract_radar.matcher import evaluate_opportunities
from contract_radar.models import AwardRecord, BusinessProfile, Solicitation, parse_date
from contract_radar.profiles import SUPPORTED_PROFILE_IDS, get_supported_profile


ACTIONABLE_LABELS = {"Pursue", "Review", "Monitor"}
DEFAULT_AS_OF = date(2026, 5, 30)


def evaluate_bid_engine(
    profile_selector: str = "all",
    offline: bool = False,
    as_of: date | None = None,
) -> dict[str, Any]:
    today = as_of or DEFAULT_AS_OF
    solicitations, awards, data_mode, warnings = _load_evaluation_data(offline=offline)
    profile_ids = _resolve_profile_ids(profile_selector)
    profile_summaries = [
        _evaluate_profile(
            profile=get_supported_profile(profile_id),
            solicitations=solicitations,
            awards=awards,
            today=today,
        )
        for profile_id in profile_ids
    ]

    return {
        "as_of": today.isoformat(),
        "data_mode": data_mode,
        "solicitations_evaluated": len(solicitations),
        "awards_loaded": len(awards),
        "profiles": profile_summaries,
        "warnings": warnings,
    }


def _evaluate_profile(
    profile: BusinessProfile,
    solicitations: list[Solicitation],
    awards: list[AwardRecord],
    today: date,
) -> dict[str, Any]:
    evaluated = evaluate_opportunities(profile, solicitations, awards, today=today)
    historical_summary = summarize_past_opportunities(profile, awards).to_dict()
    scorecard = scorecard_from_evaluated(profile, evaluated, historical_summary)
    naive_candidates = _naive_keyword_candidates(profile, solicitations)
    naive_document_numbers = {item.document_number for item in naive_candidates}
    actionable = [item for item in evaluated if item.label in ACTIONABLE_LABELS]
    baseline_false_positive_skips = [
        item
        for item in evaluated
        if item.label == "Skip"
        and item.solicitation.document_number in naive_document_numbers
        and looks_like_false_positive(item)
    ]
    top = actionable[0] if actionable else None
    naive_count = len(naive_candidates)
    actionable_count = len(actionable)
    removed_from_naive = max(0, naive_count - actionable_count)
    reduction_ratio = _shortlist_reduction_ratio(naive_count, actionable_count)

    return {
        "profile_id": profile.profile_id,
        "profile": profile.name,
        "profile_label": profile.label,
        "naive_keyword_candidate_count": naive_count,
        "bid_engine_actionable_count": actionable_count,
        "skipped_false_positives": len(baseline_false_positive_skips),
        "shortlist_reduction_ratio": reduction_ratio,
        "shortlist_reduction_percent": round(reduction_ratio * 100, 1),
        "top_opportunity": _top_opportunity(top),
        "estimated_review_hours_saved": removed_from_naive * BID_HOURS_PER_SKIPPED_OPPORTUNITY,
        "best_current_opportunity": scorecard.get("best_current_opportunity", {}),
        "buyer_division_pattern": scorecard.get("buyer_division_pattern", ""),
        "similar_award_range": scorecard.get("similar_award_range", ""),
        "similar_award_examples": scorecard.get("similar_award_examples", []),
        "false_positive_categories": scorecard.get("false_positive_categories", []),
        "capacity_downgrades": scorecard.get("capacity_downgrades", 0),
        "capacity_downgrade_reasons": scorecard.get("capacity_downgrade_reasons", []),
        "similar_awards_grounded": scorecard.get("similar_awards_grounded", 0),
        "top_insight": scorecard["top_insight"],
    }


def _naive_keyword_candidates(
    profile: BusinessProfile,
    solicitations: list[Solicitation],
) -> list[Solicitation]:
    profile_terms = _profile_keyword_terms(profile)
    candidates = []
    for solicitation in solicitations:
        solicitation_terms = meaningful_terms(
            " ".join(
                [
                    solicitation.solicitation_type,
                    solicitation.category,
                    solicitation.description,
                    solicitation.division,
                ]
            )
        )
        if profile_terms & solicitation_terms:
            candidates.append(solicitation)
    return candidates


def _profile_keyword_terms(profile: BusinessProfile) -> set[str]:
    return meaningful_terms(
        " ".join(
            [
                profile.business_type,
                *profile.skills,
                *profile.good_fit_examples,
                *profile.top_divisions,
            ]
        )
    )


def _top_opportunity(top: Any) -> dict[str, Any] | None:
    if top is None:
        return None
    return {
        "document_number": top.solicitation.document_number,
        "title": top.solicitation.description,
        "label": top.label,
        "division": top.solicitation.division,
        "buyer": top.solicitation.buyer_name,
    }


def _shortlist_reduction_ratio(naive_count: int, actionable_count: int) -> float:
    if naive_count <= 0:
        return 0.0
    return round(max(0.0, 1.0 - (actionable_count / naive_count)), 4)


def _resolve_profile_ids(profile_selector: str) -> list[str]:
    selector = str(profile_selector or "all").strip().lower()
    if selector == "all":
        return list(SUPPORTED_PROFILE_IDS)
    requested = [item.strip().lower() for item in selector.split(",") if item.strip()]
    invalid = [item for item in requested if item not in SUPPORTED_PROFILE_IDS]
    if invalid:
        supported = ", ".join(SUPPORTED_PROFILE_IDS)
        raise ValueError(f"Unsupported profile id(s): {', '.join(invalid)}. Use all or one of: {supported}")
    return requested


def _load_evaluation_data(offline: bool) -> tuple[list[Solicitation], list[AwardRecord], str, list[str]]:
    previous_offline = os.environ.get(config.OFFLINE_ENV)
    if offline:
        os.environ[config.OFFLINE_ENV] = "1"
    try:
        bundle = load_procurement_data(refresh=False)
    finally:
        if offline:
            if previous_offline is None:
                os.environ.pop(config.OFFLINE_ENV, None)
            else:
                os.environ[config.OFFLINE_ENV] = previous_offline

    data_sources = "; ".join(f"{name}={status}" for name, status in bundle.source_status.items())
    return bundle.solicitations, bundle.awards, data_sources or "Toronto Open Data", bundle.warnings


def _read_cache_records(cache_file: str, warnings: list[str]) -> list[dict[str, Any]] | None:
    path = config.CACHE_DIR / cache_file
    if not path.exists():
        warnings.append(f"Cache file missing: {path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        warnings.append(f"Cache file unreadable: {path} ({exc})")
        return None
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        warnings.append(f"Cache file has no records list: {path}")
        return None
    return [record for record in records if isinstance(record, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare a naive keyword-overlap baseline with the Live Contract Radar bid engine."
    )
    parser.add_argument("--offline", action="store_true", help="Use cached Toronto Open Data without live refresh.")
    parser.add_argument("--profiles", default="all", help="all or comma-separated supported profile ids.")
    parser.add_argument("--as-of", default=DEFAULT_AS_OF.isoformat(), help="Evaluation date. Default: 2026-05-30")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    args = parser.parse_args()

    as_of = parse_date(args.as_of)
    if as_of is None:
        print(f"FAIL: invalid --as-of date: {args.as_of}", file=sys.stderr)
        return 2

    try:
        summary = evaluate_bid_engine(args.profiles, offline=args.offline, as_of=as_of)
    except (ValueError, ProcurementDataUnavailable) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_human_summary(summary)
    return 0


def _print_human_summary(summary: dict[str, Any]) -> None:
    print("Bid Engine Baseline Evaluation")
    print(
        f"Data: {summary['data_mode']} | as of {summary['as_of']} | "
        f"{summary['solicitations_evaluated']} solicitations, {summary['awards_loaded']} awards"
    )
    for warning in summary.get("warnings") or []:
        print(f"Warning: {warning}")
    for item in summary["profiles"]:
        top = item.get("top_opportunity") or {}
        title = _compact_title(str(top.get("title") or "No actionable opportunity"))
        document_number = top.get("document_number") or "none"
        print("")
        print(f"{item['profile_label']} ({item['profile_id']})")
        print(f"  Naive keyword candidates: {item['naive_keyword_candidate_count']}")
        print(f"  Bid engine actionable: {item['bid_engine_actionable_count']}")
        print(f"  Skipped false positives: {item['skipped_false_positives']}")
        print(f"  Shortlist reduction vs naive: {item['shortlist_reduction_percent']:.1f}%")
        print(f"  Top opportunity: {document_number} - {title}")
        print(f"  Similar award range: {item.get('similar_award_range') or 'insufficient history'}")
        print(f"  Buyer/division pattern: {item.get('buyer_division_pattern') or 'not available'}")
        print(f"  Similar awards grounded: {item.get('similar_awards_grounded', 0)}")
        categories = _format_false_positive_categories(item.get("false_positive_categories") or [])
        if categories:
            print(f"  False-positive categories: {categories}")
        if item.get("capacity_downgrades"):
            print(f"  Capacity downgrades: {item['capacity_downgrades']} ({_format_capacity_reasons(item.get('capacity_downgrade_reasons') or [])})")
        print(f"  Estimated review hours saved: {item['estimated_review_hours_saved']}")
        print(f"  Judge insight: {item['top_insight']}")


def _compact_title(title: str, limit: int = 110) -> str:
    clean = " ".join(title.split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 3].rstrip()}..."


def _format_false_positive_categories(categories: list[dict[str, Any]]) -> str:
    parts = []
    for category in categories[:3]:
        label = str(category.get("category") or "Uncategorized")
        blocker = str(category.get("blocker") or "weak evidence")
        count = int(category.get("count") or 0)
        parts.append(f"{label}/{blocker} ({count})")
    return "; ".join(parts)


def _format_capacity_reasons(reasons: list[dict[str, Any]]) -> str:
    parts = []
    for reason in reasons[:2]:
        label = str(reason.get("reason") or "owner review required")
        count = int(reason.get("count") or 0)
        parts.append(f"{label} x{count}")
    return "; ".join(parts) or "owner review required"


if __name__ == "__main__":
    raise SystemExit(main())
