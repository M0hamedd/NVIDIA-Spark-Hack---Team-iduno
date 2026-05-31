from __future__ import annotations

import hashlib
import time
from datetime import date
from threading import Lock
from typing import Any

from contract_radar.models import EvaluatedOpportunity, PipelineMetrics
from contract_radar.profiles import profile_from_payload, supported_profiles


class ContractRadarService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._last_scan: dict[str, Any] | None = None
        self._market_model_cache: dict[str, Any] = {}

    def health(self) -> dict[str, Any]:
        from contract_radar.gpu import gpu_status
        from contract_radar.nemotron import nemotron_status
        from contract_radar.ranker import ranker_status

        gpu = gpu_status()
        nemotron = nemotron_status()
        ranker = ranker_status()
        active_tools = []
        if gpu.get("rapids_cudf_available"):
            active_tools.append("RAPIDS/cuDF")
        if nemotron.get("available"):
            active_tools.append("NIM/Nemotron")
        nvidia_stack_active = bool(active_tools)
        if nvidia_stack_active:
            spark_story = (
                "DGX Spark is active through " + ", ".join(active_tools) + ". Procurement data, "
                "business strategy, retrieval, and extraction stay local."
            )
        elif ranker.get("available"):
            spark_story = (
                "Local award-history ML is active for procurement intelligence; NVIDIA hooks remain ready "
                "for RAPIDS/cuDF or local NIM."
            )
        else:
            spark_story = (
                "Local ranker dependencies are missing; install requirements before scanning. "
                "NVIDIA hooks remain ready for RAPIDS/cuDF or local NIM."
            )
        return {
            "status": "ok",
            "project": "Live Contract Radar",
            "track": "Economic Systems",
            "labels": ["Pursue", "Review", "Monitor", "Skip"],
            "priority_modes": ["best_win_chance", "best_fit", "highest_value"],
            "supported_profiles": supported_profiles(),
            "gpu": gpu,
            "nemotron": nemotron,
            "ranker": ranker,
            "nvidia_stack_active": nvidia_stack_active,
            "active_nvidia_tools": active_tools,
            "rapids_cudf_available": bool(gpu.get("rapids_cudf_available")),
            "rapids_mode": gpu.get("rapids_mode", "python_fallback"),
            "nim_mode": nemotron.get("nim_mode", "deterministic_fallback"),
            "spark_story": spark_story,
            "endpoints": ["/api/scan", "/api/simulate", "/api/approve"],
        }

    def scan(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        from contract_radar.data import load_procurement_data
        from contract_radar.backtest import scorecard_from_evaluated
        from contract_radar.history import summarize_past_opportunities
        from contract_radar.matcher import evaluate_opportunities, normalize_priority_mode
        from contract_radar.nemotron import enrich_top_opportunities_with_stats
        from contract_radar.ranker import apply_market_intelligence

        start = time.perf_counter()
        profile = profile_from_payload(payload or {})
        today = _payload_date(payload) or date.today()
        priority_mode = normalize_priority_mode((payload or {}).get("priority_mode"))
        data_bundle = load_procurement_data(refresh=bool((payload or {}).get("refresh")))
        historical_summary = summarize_past_opportunities(profile, data_bundle.awards).to_dict()
        evaluated = evaluate_opportunities(
            profile,
            data_bundle.solicitations,
            data_bundle.awards,
            today=today,
            priority_mode=priority_mode,
        )
        market_model = self._market_model_for(profile, data_bundle.awards)
        evaluated = apply_market_intelligence(
            profile=profile,
            opportunities=evaluated,
            awards=data_bundle.awards,
            trained_model=market_model,
            today=today,
            priority_mode=priority_mode,
        )
        enriched, nemotron_mode, nemotron_stats = enrich_top_opportunities_with_stats(profile, evaluated[:5])
        enriched_by_doc = {item.solicitation.document_number: item for item in enriched}
        evaluated = [enriched_by_doc.get(item.solicitation.document_number, item) for item in evaluated]
        skipped = _prioritized_skips(evaluated)
        scorecard = scorecard_from_evaluated(profile, evaluated, historical_summary)
        metrics = _metrics(data_bundle, evaluated, start, nemotron_mode, nemotron_stats, market_model.summary)
        metrics_dict = metrics.to_dict()
        metrics_dict["priority_mode"] = priority_mode
        result = {
            "business_profile": profile.to_dict(),
            "as_of": today.isoformat(),
            "priority_mode": priority_mode,
            "historical_summary": historical_summary,
            "top_opportunities": [item.to_dict() for item in evaluated if item.label == "Pursue"][:5],
            "watchlist": [item.to_dict() for item in evaluated if item.label in {"Review", "Monitor"}][:8],
            "skipped": [item.to_dict() for item in skipped[:10]],
            "all_evaluated": [item.to_dict() for item in evaluated[:40]],
            "market_model": market_model.summary,
            "insight_scorecard": scorecard,
            "metrics": metrics_dict,
        }
        with self._lock:
            self._last_scan = result
        return result

    def simulate(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        from contract_radar.simulator import simulate_month

        scan_result = self.scan(payload or {})
        timeline = simulate_month(scan_result, days=int((payload or {}).get("days") or 30))
        scan_result["timeline"] = timeline
        return scan_result

    def approve(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        from contract_radar.packet import create_approval_packet

        payload = payload or {}
        approved = bool(payload.get("approved"))
        opportunity_id = str(payload.get("opportunity_id") or "")
        scan_result = self._last_scan or self.scan(payload)
        opportunities = [
            item
            for item in scan_result.get("all_evaluated", [])
            if isinstance(item, dict) and item.get("label") != "Skip"
        ]
        selected = _find_opportunity(opportunities, opportunity_id)
        if selected is None and not opportunity_id and opportunities:
            selected = opportunities[0]
        if selected is None:
            raise ValueError("No non-skipped opportunity is available for approval.")
        packet = create_approval_packet(scan_result["business_profile"], selected, approved)
        return {"packet": packet.to_dict(), "approved": approved}

    def _market_model_for(self, profile: Any, awards: list[Any]) -> Any:
        from contract_radar.ranker import train_award_history_market_model

        key = _market_cache_key(profile, awards)
        with self._lock:
            cached = self._market_model_cache.get(key)
        if cached is not None:
            return cached

        trained = train_award_history_market_model(profile, awards)
        with self._lock:
            self._market_model_cache[key] = trained
        return trained


def _payload_date(payload: dict[str, Any] | None) -> date | None:
    from contract_radar.models import parse_date

    return parse_date((payload or {}).get("as_of"))


def _metrics(
    data_bundle: Any,
    evaluated: list[EvaluatedOpportunity],
    start: float,
    nemotron_mode: str,
    nemotron_stats: dict[str, Any],
    market_summary: dict[str, Any],
) -> PipelineMetrics:
    label_counts: dict[str, int] = {}
    for item in evaluated:
        label_counts[item.label] = label_counts.get(item.label, 0) + 1
    runtime_ms = int((time.perf_counter() - start) * 1000)
    loaded_records = len(data_bundle.solicitations) + len(data_bundle.awards)
    runtime_seconds = max(runtime_ms / 1000, 0.001)
    shortlisted_for_model = int(nemotron_stats.get("shortlisted_for_model") or 0)
    model_calls_attempted = int(nemotron_stats.get("model_calls_attempted") or 0)
    model_calls_successful = int(nemotron_stats.get("model_calls_successful") or 0)
    model_calls_avoided = (
        max(0, len(evaluated) - shortlisted_for_model)
        + int(nemotron_stats.get("model_calls_avoided_by_preflight") or 0)
        + int(nemotron_stats.get("model_calls_avoided_by_failure") or 0)
    )
    briefs_generated = int(nemotron_stats.get("briefs_generated") or 0)
    label_changes_after_extraction = int(nemotron_stats.get("label_changes_after_extraction") or 0)
    shortlist_reduction_ratio = (
        1.0 - (shortlisted_for_model / len(evaluated)) if evaluated else 0.0
    )
    active_nvidia_tools: list[str] = []
    rapids_mode = getattr(data_bundle, "rapids_mode", "python_fallback")
    if rapids_mode == "rapids_cudf":
        active_nvidia_tools.append("RAPIDS/cuDF")
    if nemotron_mode == "local_nim":
        active_nvidia_tools.append("NIM/Nemotron")
    return PipelineMetrics(
        solicitations_loaded=len(data_bundle.solicitations),
        awards_loaded=len(data_bundle.awards),
        opportunities_evaluated=len(evaluated),
        rejected_count=label_counts.get("Skip", 0),
        top_candidate_count=label_counts.get("Pursue", 0),
        runtime_ms=runtime_ms,
        records_per_second=round(loaded_records / runtime_seconds, 2),
        shortlist_reduction_ratio=round(shortlist_reduction_ratio, 4),
        model_calls_attempted=model_calls_attempted,
        model_calls_successful=model_calls_successful,
        model_calls_avoided=model_calls_avoided,
        briefs_generated=briefs_generated,
        label_changes_after_extraction=label_changes_after_extraction,
        market_model_mode=str(market_summary.get("mode") or "sklearn_award_history"),
        market_model_examples=int(market_summary.get("examples") or 0),
        market_model_positive_examples=int(market_summary.get("positive_examples") or 0),
        market_model_precision_at_10=float(market_summary.get("precision_at_10") or 0.0),
        market_model_top_decile_lift=float(market_summary.get("top_decile_lift") or 0.0),
        market_model_average_precision=float(market_summary.get("average_precision") or 0.0),
        data_sources=data_bundle.source_status,
        label_counts=label_counts,
        engine=getattr(data_bundle, "engine", "python"),
        rapids_mode=rapids_mode,
        nemotron_mode=nemotron_mode,
        nvidia_stack_active=bool(active_nvidia_tools),
        active_nvidia_tools=active_nvidia_tools,
        fetched_at=getattr(data_bundle, "fetched_at", ""),
        warnings=getattr(data_bundle, "warnings", []),
    )


def _market_cache_key(profile: Any, awards: list[Any]) -> str:
    latest = max(
        (award.award_date.isoformat() for award in awards if getattr(award, "award_date", None)),
        default="no-date",
    )
    digest = hashlib.sha256()
    for award in awards[:20] + awards[-20:]:
        digest.update(str(getattr(award, "document_number", "")).encode("utf-8"))
        digest.update(str(getattr(award, "supplier", "")).encode("utf-8"))
        digest.update(str(getattr(award, "award_value", "")).encode("utf-8"))
    return f"{getattr(profile, 'profile_id', '')}:{len(awards)}:{latest}:{digest.hexdigest()[:16]}"


def _find_opportunity(opportunities: list[dict[str, Any]], opportunity_id: str) -> dict[str, Any] | None:
    if not opportunities:
        return None
    if not opportunity_id:
        return opportunities[0]
    for item in opportunities:
        solicitation = item.get("solicitation", {})
        if solicitation.get("document_number") == opportunity_id:
            return item
    return None


def _prioritized_skips(evaluated: list[EvaluatedOpportunity]) -> list[EvaluatedOpportunity]:
    skipped = [item for item in evaluated if item.label == "Skip"]
    return sorted(
        skipped,
        key=lambda item: (
            item.days_until_deadline is not None and item.days_until_deadline < 0,
            -(item.rank_score or 0),
            item.days_until_deadline if item.days_until_deadline is not None else 9999,
            item.solicitation.document_number,
        ),
    )
