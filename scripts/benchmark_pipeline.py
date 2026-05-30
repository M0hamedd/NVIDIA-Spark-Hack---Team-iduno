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
    parser.add_argument("--offline", action="store_true", help="Force deterministic offline/sample data.")
    parser.add_argument("--refresh", action="store_true", help="Refresh Toronto Open Data before benchmarking.")
    parser.add_argument("--repeat", type=int, default=10, help="Number of scan repetitions. Default: 10")
    parser.add_argument("--priority-mode", default="best_win_chance", help="Priority mode for scans.")
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
        scans.append(
            service.scan(
                {
                    "refresh": bool(args.refresh and index == 0),
                    "priority_mode": args.priority_mode,
                }
            )
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    summary = _summary(scans, repeat, elapsed_ms)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        _print_text_summary(summary)
    return 0


def _summary(scans: list[dict[str, Any]], repeat: int, elapsed_ms: int) -> dict[str, Any]:
    last_scan = scans[-1]
    metrics = last_scan.get("metrics") or {}
    scorecard = last_scan.get("insight_scorecard") or {}
    avg_runtime_ms = round(sum((scan.get("metrics") or {}).get("runtime_ms", 0) for scan in scans) / repeat, 2)
    avg_records_per_second = round(
        sum((scan.get("metrics") or {}).get("records_per_second", 0.0) for scan in scans) / repeat,
        2,
    )
    return {
        "repeat": repeat,
        "total_elapsed_ms": elapsed_ms,
        "average_scan_runtime_ms": avg_runtime_ms,
        "average_records_per_second": avg_records_per_second,
        "last_scan": {
            "solicitations_loaded": metrics.get("solicitations_loaded", 0),
            "awards_loaded": metrics.get("awards_loaded", 0),
            "opportunities_evaluated": metrics.get("opportunities_evaluated", 0),
            "rejected_count": metrics.get("rejected_count", 0),
            "top_candidate_count": metrics.get("top_candidate_count", 0),
            "shortlist_reduction_ratio": metrics.get("shortlist_reduction_ratio", 0.0),
            "model_calls_attempted": metrics.get("model_calls_attempted", 0),
            "model_calls_avoided": metrics.get("model_calls_avoided", 0),
            "rapids_mode": metrics.get("rapids_mode", "python_fallback"),
            "nemotron_mode": metrics.get("nemotron_mode", "deterministic_fallback"),
            "nvidia_stack_active": bool(metrics.get("nvidia_stack_active")),
            "active_nvidia_tools": metrics.get("active_nvidia_tools", []),
        },
        "insight_scorecard": {
            "realistic_historical_opportunities": scorecard.get("realistic_historical_opportunities", 0),
            "false_positives_skipped": scorecard.get("false_positives_skipped", 0),
            "similar_awards_grounded": scorecard.get("similar_awards_grounded", 0),
            "capacity_downgrades": scorecard.get("capacity_downgrades", 0),
            "estimated_bid_hours_saved": scorecard.get("estimated_bid_hours_saved", 0),
            "top_insight": scorecard.get("top_insight", ""),
        },
    }


def _print_text_summary(summary: dict[str, Any]) -> None:
    last = summary["last_scan"]
    scorecard = summary["insight_scorecard"]
    print("Live Contract Radar Benchmark")
    print(f"Repeats: {summary['repeat']}")
    print(f"Average scan runtime: {summary['average_scan_runtime_ms']} ms")
    print(f"Average throughput: {summary['average_records_per_second']} records/sec")
    print(
        "Last scan: "
        f"{last['solicitations_loaded']} solicitations, {last['awards_loaded']} awards, "
        f"{last['rejected_count']} rejected, {last['top_candidate_count']} pursue candidates"
    )
    print(
        "NVIDIA path: "
        f"RAPIDS={last['rapids_mode']}, NIM={last['nemotron_mode']}, "
        f"active={', '.join(last['active_nvidia_tools']) if last['active_nvidia_tools'] else 'fallback'}"
    )
    print(
        "Model efficiency: "
        f"{last['model_calls_attempted']} attempted, {last['model_calls_avoided']} avoided, "
        f"shortlist reduction={last['shortlist_reduction_ratio']:.0%}"
    )
    print(
        "Insight scorecard: "
        f"{scorecard['realistic_historical_opportunities']} historical realistic, "
        f"{scorecard['false_positives_skipped']} false positives skipped, "
        f"{scorecard['similar_awards_grounded']} similar awards grounded, "
        f"{scorecard['estimated_bid_hours_saved']} bid-review hours saved"
    )
    if scorecard.get("top_insight"):
        print(f"Judge insight: {scorecard['top_insight']}")


if __name__ == "__main__":
    raise SystemExit(main())
