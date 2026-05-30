from __future__ import annotations

from threading import Lock
from typing import Any

from sparkterritory.config import DATASETS, NIM_BASE_URL, NIM_MODEL, SCORE_WEIGHTS
from sparkterritory.data import DataSignals, cudf_available, load_signals
from sparkterritory.nemotron import NemotronClient
from sparkterritory.scoring import (
    BusinessProfile,
    downtown_tradeoff,
    score_neighbourhoods,
    split_recommendations,
    weights_for_profile,
)


class RecommendationService:
    def __init__(self) -> None:
        self._signals: DataSignals | None = None
        self._lock = Lock()
        self._nemotron = NemotronClient()

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "track": "Economic Systems",
            "rapids_cudf_available": cudf_available(),
            "dataframe_engine": self._signals.dataframe_engine if self._signals else ("rapids_cudf" if cudf_available() else "python_csv_fallback"),
            "nim_base_url": NIM_BASE_URL,
            "nim_model": NIM_MODEL,
            "datasets": {key: value["package"] for key, value in DATASETS.items()},
        }

    def recommend(self, payload: dict[str, Any]) -> dict[str, Any]:
        profile = BusinessProfile.from_payload(payload)
        signals = self._get_signals()
        scored = score_neighbourhoods(profile, signals)
        target_now, future_expansion = split_recommendations(scored)
        tradeoff = downtown_tradeoff(scored)
        metadata = {
            "track": "Economic Systems",
            "dataframe_engine": signals.dataframe_engine,
            "spark_story": (
                "DGX Spark runs the local Toronto Open Data scoring pipeline and local Nemotron/NIM inference. "
                "This keeps business profiles and recommendations local while enabling fast what-if scenario simulation."
            ),
            "score_weights": SCORE_WEIGHTS,
            "applied_score_weights": weights_for_profile(profile),
            "pipeline_steps": [
                {"label": "Toronto Open Data loaded", "detail": "permits, development, profiles"},
                {"label": "GPU-ready feature engineering", "detail": signals.dataframe_engine},
                {"label": "Opportunity zones scored", "detail": "demand, growth, prospects, feasibility"},
                {"label": "Local expansion brief prepared", "detail": "NIM if available, deterministic fallback otherwise"},
            ],
            "source_status": signals.source_status,
            "warnings": signals.warnings,
        }
        agent = self._nemotron.generate_report(profile, target_now, future_expansion, tradeoff, metadata)
        return {
            "project": "SparkTerritory AI",
            "business_profile": profile.__dict__,
            "ranked_neighbourhoods": target_now,
            "future_expansion_neighbourhoods": future_expansion,
            "downtown_tradeoff": tradeoff,
            "agent_mode": agent["mode"],
            "agent_model": agent["model"],
            "agent_report": agent["report"],
            "metadata": metadata,
        }

    def _get_signals(self) -> DataSignals:
        with self._lock:
            if self._signals is None:
                self._signals = load_signals()
            return self._signals
