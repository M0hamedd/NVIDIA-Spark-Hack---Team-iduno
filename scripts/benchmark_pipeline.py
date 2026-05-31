from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark Live Contract Radar's local scan, shortlist, NVIDIA, and evidence pipeline."
    )
    parser.add_argument("--offline", action="store_true", help="Use cached Toronto Open Data without live refresh.")
    parser.add_argument("--refresh", action="store_true", help="Refresh Toronto Open Data before benchmarking.")
    parser.add_argument("--repeat", type=int, default=10, help="Number of scan repetitions. Default: 10")
    parser.add_argument("--profile", default="", help="Supported business profile id to benchmark.")
    parser.add_argument("--priority-mode", default="best_win_chance", help="Priority mode for scans.")
    parser.add_argument(
        "--require-nvidia",
        action="store_true",
        help="Fail if the last scan did not use active NVIDIA tools. Intended for judged demo readiness.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    args = parser.parse_args()

    if args.offline:
        os.environ["CONTRACT_RADAR_OFFLINE"] = "1"

    from contract_radar.service import ContractRadarService

    repeat = max(1, args.repeat)
    service = ContractRadarService()
    scans: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index in range(repeat):
        payload: dict[str, Any] = {
            "refresh": bool(args.refresh and index == 0),
            "priority_mode": args.priority_mode,
        }
        if args.profile:
            payload["profile_id"] = args.profile
        scans.append(
            service.scan(payload)
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    summary = _summary(scans, repeat, elapsed_ms)

    if args.require_nvidia:
        gate_error = _nvidia_gate_error(summary)
        if gate_error:
            print(gate_error, file=sys.stderr)
            return 2

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_text_summary(summary)
    return 0


def _summary(scans: list[dict[str, Any]], repeat: int, elapsed_ms: int) -> dict[str, Any]:
    last_scan = scans[-1]
    metrics = last_scan.get("metrics") or {}
    scorecard = last_scan.get("insight_scorecard") or {}
    profile = last_scan.get("business_profile") or {}
    solicitations_loaded = int(metrics.get("solicitations_loaded", 0) or 0)
    awards_loaded = int(metrics.get("awards_loaded", 0) or 0)
    total_local_records_processed = solicitations_loaded + awards_loaded
    records_per_second = float(metrics.get("records_per_second", 0.0) or 0.0)
    shortlist_reduction_ratio = float(metrics.get("shortlist_reduction_ratio", 0.0) or 0.0)
    active_nvidia_tools = [
        str(tool)
        for tool in metrics.get("active_nvidia_tools", [])
        if str(tool).strip()
    ]
    data_source_statuses = dict(metrics.get("data_sources") or {})
    active_nvidia_path = _active_nvidia_path(metrics, active_nvidia_tools)
    avg_runtime_ms = round(sum((scan.get("metrics") or {}).get("runtime_ms", 0) for scan in scans) / repeat, 2)
    avg_records_per_second = round(
        sum((scan.get("metrics") or {}).get("records_per_second", 0.0) for scan in scans) / repeat,
        2,
    )
    return {
        "repeat": repeat,
        "profile": {
            "profile_id": profile.get("profile_id", ""),
            "label": profile.get("label", ""),
            "name": profile.get("name", ""),
        },
        "priority_mode": last_scan.get("priority_mode", ""),
        "total_elapsed_ms": elapsed_ms,
        "average_scan_runtime_ms": avg_runtime_ms,
        "average_records_per_second": avg_records_per_second,
        "local_record_replay": {
            "solicitations_loaded": solicitations_loaded,
            "awards_loaded": awards_loaded,
            "total_local_records_processed": total_local_records_processed,
            "records_per_second": records_per_second,
            "average_records_per_second": avg_records_per_second,
            "data_source_statuses": data_source_statuses,
        },
        "performance_proof": {
            "opportunities_evaluated": metrics.get("opportunities_evaluated", 0),
            "shortlist_reduction_ratio": shortlist_reduction_ratio,
            "shortlist_reduction_percent": round(shortlist_reduction_ratio * 100, 2),
            "model_calls_attempted": metrics.get("model_calls_attempted", 0),
            "model_calls_successful": metrics.get("model_calls_successful", 0),
            "model_calls_avoided": metrics.get("model_calls_avoided", 0),
            "briefs_generated": metrics.get("briefs_generated", 0),
            "label_changes_after_extraction": metrics.get("label_changes_after_extraction", 0),
            "market_model_mode": metrics.get("market_model_mode", "not_scored"),
            "market_model_examples": metrics.get("market_model_examples", 0),
            "market_model_precision_at_10": metrics.get("market_model_precision_at_10", 0.0),
            "market_model_top_decile_lift": metrics.get("market_model_top_decile_lift", 0.0),
            "active_nvidia_path": active_nvidia_path,
            "nvidia_stack_active": bool(metrics.get("nvidia_stack_active")),
            "active_nvidia_tools": active_nvidia_tools,
            "rapids_mode": metrics.get("rapids_mode", "python_fallback"),
            "nemotron_mode": metrics.get("nemotron_mode", "deterministic_fallback"),
            "cuopt_mode": metrics.get("cuopt_mode", "greedy_fallback"),
        },
        "last_scan": {
            "solicitations_loaded": solicitations_loaded,
            "awards_loaded": awards_loaded,
            "total_local_records_processed": total_local_records_processed,
            "records_per_second": records_per_second,
            "opportunities_evaluated": metrics.get("opportunities_evaluated", 0),
            "rejected_count": metrics.get("rejected_count", 0),
            "top_candidate_count": metrics.get("top_candidate_count", 0),
            "shortlist_reduction_ratio": shortlist_reduction_ratio,
            "shortlist_reduction_percent": round(shortlist_reduction_ratio * 100, 2),
            "model_calls_attempted": metrics.get("model_calls_attempted", 0),
            "model_calls_successful": metrics.get("model_calls_successful", 0),
            "model_calls_avoided": metrics.get("model_calls_avoided", 0),
            "briefs_generated": metrics.get("briefs_generated", 0),
            "label_changes_after_extraction": metrics.get("label_changes_after_extraction", 0),
            "market_model_mode": metrics.get("market_model_mode", "not_scored"),
            "market_model_examples": metrics.get("market_model_examples", 0),
            "market_model_precision_at_10": metrics.get("market_model_precision_at_10", 0.0),
            "market_model_top_decile_lift": metrics.get("market_model_top_decile_lift", 0.0),
            "active_nvidia_path": active_nvidia_path,
            "data_source_statuses": data_source_statuses,
            "rapids_mode": metrics.get("rapids_mode", "python_fallback"),
            "nemotron_mode": metrics.get("nemotron_mode", "deterministic_fallback"),
            "cuopt_mode": metrics.get("cuopt_mode", "greedy_fallback"),
            "nvidia_stack_active": bool(metrics.get("nvidia_stack_active")),
            "active_nvidia_tools": active_nvidia_tools,
        },
        "insight_scorecard": {
            "realistic_historical_opportunities": scorecard.get("realistic_historical_opportunities", 0),
            "false_positives_skipped": scorecard.get("false_positives_skipped", 0),
            "false_positive_categories": scorecard.get("false_positive_categories", []),
            "similar_awards_grounded": scorecard.get("similar_awards_grounded", 0),
            "similar_award_range": scorecard.get("similar_award_range", ""),
            "similar_award_examples": scorecard.get("similar_award_examples", []),
            "capacity_downgrades": scorecard.get("capacity_downgrades", 0),
            "capacity_downgrade_reasons": scorecard.get("capacity_downgrade_reasons", []),
            "capacity_examples": scorecard.get("capacity_examples", []),
            "estimated_bid_hours_saved": scorecard.get("estimated_bid_hours_saved", 0),
            "best_current_opportunity": scorecard.get("best_current_opportunity", {}),
            "buyer_division_pattern": scorecard.get("buyer_division_pattern", ""),
            "top_insight": scorecard.get("top_insight", ""),
        },
    }


def _active_nvidia_path(metrics: dict[str, Any], active_nvidia_tools: list[str]) -> str:
    if active_nvidia_tools:
        return ", ".join(active_nvidia_tools)
    rapids_mode = metrics.get("rapids_mode", "python_fallback")
    nemotron_mode = metrics.get("nemotron_mode", "deterministic_fallback")
    cuopt_mode = metrics.get("cuopt_mode", "greedy_fallback")
    return f"fallback (RAPIDS={rapids_mode}, NIM={nemotron_mode}, cuOpt={cuopt_mode})"


def _nvidia_gate_error(summary: dict[str, Any]) -> str:
    last = summary["last_scan"]
    if last["nvidia_stack_active"] and last["active_nvidia_tools"]:
        return ""
    return (
        "NVIDIA proof gate failed: last scan reported no active NVIDIA tools "
        f"(nvidia_stack_active={str(last['nvidia_stack_active']).lower()}, "
        f"active_nvidia_tools={last['active_nvidia_tools']}). "
        "Start RAPIDS/cuDF, local NIM/Nemotron, or cuOpt, then rerun without --offline or with a reachable "
        "local NVIDIA path; omit --require-nvidia for deterministic fallback demos."
    )


def _print_text_summary(summary: dict[str, Any]) -> None:
    last = summary["last_scan"]
    scorecard = summary["insight_scorecard"]
    profile = summary["profile"]
    print("Live Contract Radar Benchmark")
    print(f"Profile: {profile['label']} ({profile['profile_id']})")
    print(f"Repeats: {summary['repeat']}")
    print(f"Average scan runtime: {summary['average_scan_runtime_ms']} ms")
    print(f"Average throughput: {summary['average_records_per_second']} records/sec")
    print(
        "Local record replay: "
        f"{last['total_local_records_processed']} total records "
        f"({last['solicitations_loaded']} solicitations + {last['awards_loaded']} awards) "
        f"at {last['records_per_second']} records/sec"
    )
    print(f"Data sources: {_format_data_sources(last['data_source_statuses'])}")
    print(
        "Last scan: "
        f"{last['solicitations_loaded']} solicitations, {last['awards_loaded']} awards, "
        f"{last['rejected_count']} rejected, {last['top_candidate_count']} pursue candidates"
    )
    print(
        "NVIDIA path: "
        f"RAPIDS={last['rapids_mode']}, NIM={last['nemotron_mode']}, cuOpt={last['cuopt_mode']}, "
        f"active={last['active_nvidia_path']}"
    )
    print(
        "Model efficiency: "
        f"{last['model_calls_attempted']} attempted, {last['model_calls_successful']} successful, "
        f"{last['model_calls_avoided']} avoided, {last['briefs_generated']} brief(s), "
        f"{last['label_changes_after_extraction']} label change(s), "
        f"shortlist reduction={last['shortlist_reduction_percent']:.2f}%"
    )
    print(
        "Market model: "
        f"{last['market_model_mode']}, {last['market_model_examples']} examples, "
        f"precision@10={float(last['market_model_precision_at_10']):.3f}, "
        f"top-decile lift={float(last['market_model_top_decile_lift']):.2f}x"
    )
    print(
        "Insight scorecard: "
        f"{scorecard['realistic_historical_opportunities']} historical realistic, "
        f"{scorecard['false_positives_skipped']} false positives skipped, "
        f"{scorecard['similar_awards_grounded']} similar awards grounded, "
        f"{scorecard['estimated_bid_hours_saved']} bid-review hours saved"
    )
    best = scorecard.get("best_current_opportunity") or {}
    if best.get("document_number"):
        print(
            "Best current opportunity: "
            f"{best['document_number']} - {_compact_title(str(best.get('title') or 'No title'))}"
        )
    if scorecard.get("similar_award_range"):
        print(f"Similar award range: {scorecard['similar_award_range']}")
    categories = _format_false_positive_categories(scorecard.get("false_positive_categories") or [])
    if categories:
        print(f"False-positive categories: {categories}")
    if scorecard.get("top_insight"):
        print(f"Judge insight: {scorecard['top_insight']}")


def _format_data_sources(data_source_statuses: dict[str, str]) -> str:
    if not data_source_statuses:
        return "unknown"
    return "; ".join(f"{name}={status}" for name, status in data_source_statuses.items())


def _format_false_positive_categories(categories: list[dict[str, Any]]) -> str:
    parts = []
    for category in categories[:3]:
        label = str(category.get("category") or "Uncategorized")
        blocker = str(category.get("blocker") or "weak evidence")
        count = int(category.get("count") or 0)
        parts.append(f"{label}/{blocker} ({count})")
    return "; ".join(parts)


def _compact_title(title: str, limit: int = 110) -> str:
    clean = " ".join(title.split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 3].rstrip()}..."


if __name__ == "__main__":
    raise SystemExit(main())
