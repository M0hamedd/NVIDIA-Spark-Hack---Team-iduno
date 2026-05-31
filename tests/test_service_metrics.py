from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from contract_radar.nemotron import reset_nim_preflight_cache
from contract_radar.service import ContractRadarService


class ServiceMetricsTests(unittest.TestCase):
    def test_health_and_scan_expose_judging_metrics(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CONTRACT_RADAR_OFFLINE": "1",
                "NIM_BASE_URL": "http://127.0.0.1:9/v1",
                "NIM_PREFLIGHT_TIMEOUT_SECONDS": "0.05",
            },
            clear=False,
        ):
            reset_nim_preflight_cache()
            service = ContractRadarService()
            health = service.health()
            scan = service.scan({})

        self.assertIn("nvidia_stack_active", health)
        self.assertIn("active_nvidia_tools", health)
        self.assertIn("rapids_mode", health)
        self.assertIn("nim_mode", health)
        self.assertIn("ranker", health)
        self.assertIn("spark_story", health)
        self.assertTrue(health["ranker"]["available"])

        metrics = scan["metrics"]
        self.assertGreater(metrics["records_per_second"], 0)
        self.assertGreaterEqual(metrics["shortlist_reduction_ratio"], 0)
        self.assertGreaterEqual(metrics["model_calls_avoided"], 1)
        self.assertIn("model_calls_successful", metrics)
        self.assertIn("briefs_generated", metrics)
        self.assertIn("label_changes_after_extraction", metrics)
        self.assertEqual(metrics["market_model_mode"], "sklearn_award_history")
        self.assertGreater(metrics["market_model_examples"], 0)
        self.assertGreaterEqual(metrics["market_model_precision_at_10"], 0)
        self.assertIn("market_model", scan)
        self.assertIn("technical_depth_proof", scan)
        self.assertGreaterEqual(len(scan["technical_depth_proof"]), 5)
        self.assertIn("Pipeline:", scan["technical_depth_proof"][0])
        self.assertTrue(
            any("Award-history ML" in line for line in scan["technical_depth_proof"])
        )
        self.assertIn("rapids_mode", metrics)
        self.assertIn("nvidia_stack_active", metrics)
        self.assertIn("insight_scorecard", scan)
        self.assertGreaterEqual(scan["insight_scorecard"]["false_positives_skipped"], 1)
        self.assertTrue(scan["insight_scorecard"]["best_current_opportunity"]["document_number"])
        self.assertGreater(len(scan["insight_scorecard"]["similar_award_examples"]), 0)
        self.assertGreater(len(scan["insight_scorecard"]["false_positive_categories"]), 0)
        first = (scan["top_opportunities"] or scan["watchlist"] or scan["all_evaluated"])[0]
        self.assertEqual(first["market_fit"]["source"], "sklearn_award_history")


if __name__ == "__main__":
    unittest.main()
