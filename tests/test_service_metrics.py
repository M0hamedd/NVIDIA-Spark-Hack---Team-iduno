from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contract_radar import config
from contract_radar.nemotron import reset_nim_preflight_cache
from contract_radar.precomputed import write_precomputed_scan
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
        self.assertEqual(first["bid_recommendation"]["source"], "trained_award_value_model")
        self.assertGreater(first["bid_recommendation"]["recommended_bid"], 0)
        self.assertGreater(first["predicted_bid"], 0)
        self.assertGreaterEqual(first["fit_probability"], 0)
        self.assertIn("rag_evidence", first)
        self.assertGreater(len(first["rag_evidence"]["analogs"]), 0)
        self.assertIn("simulation_summary", first)
        self.assertGreater(first["simulation_summary"]["iterations"], 0)
        self.assertIn("portfolio_decision", first)
        self.assertIn(first["portfolio_decision"]["decision"], {"Pursue Now", "Pursue If Capacity Frees", "Review", "Monitor", "Pass"})
        self.assertIn("value_model_mode", metrics)
        self.assertIn("rag_mode", metrics)
        self.assertIn("cuopt_mode", metrics)

    def test_scan_can_replay_precomputed_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(config, "PRECOMPUTED_DIR", Path(tmpdir)):
                write_precomputed_scan(
                    scan_result={
                        "business_profile": {"profile_id": "road_civil_infrastructure"},
                        "priority_mode": "best_win_chance",
                        "metrics": {"runtime_ms": 123, "warnings": []},
                        "top_opportunities": [],
                        "watchlist": [],
                        "skipped": [],
                        "all_evaluated": [],
                    },
                    profile_id="road_civil_infrastructure",
                    priority_mode="best_win_chance",
                    as_of=None,
                )
                with patch.dict(os.environ, {"CONTRACT_RADAR_USE_PRECOMPUTED_SCAN": "1"}, clear=False):
                    with patch("contract_radar.data.load_procurement_data") as load_data:
                        scan = ContractRadarService().scan(
                            {
                                "profile_id": "road_civil_infrastructure",
                                "priority_mode": "best_win_chance",
                            }
                        )

                load_data.assert_not_called()
                self.assertTrue(scan["metrics"]["precomputed_scan_replay"])
                self.assertIn("Precomputed scan replay", scan["metrics"]["warnings"][0])

    def test_scan_result_is_cached_after_first_run(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CONTRACT_RADAR_OFFLINE": "1",
                "CONTRACT_RADAR_DISABLE_NEMOTRON": "1",
            },
            clear=False,
        ):
            service = ContractRadarService()
            first = service.scan({"profile_id": "road_civil_infrastructure"})
            with patch("contract_radar.data.load_procurement_data") as load_data:
                second = service.scan({"profile_id": "road_civil_infrastructure"})

        load_data.assert_not_called()
        self.assertFalse(first["metrics"].get("scan_result_cache_hit", False))
        self.assertTrue(second["metrics"]["scan_result_cache_hit"])
        self.assertEqual(first["business_profile"]["profile_id"], second["business_profile"]["profile_id"])

    def test_profile_variant_reuses_artifacts_without_exact_result_cache(self) -> None:
        with patch.dict(
            os.environ,
            {
                "CONTRACT_RADAR_OFFLINE": "1",
                "CONTRACT_RADAR_DISABLE_NEMOTRON": "1",
            },
            clear=False,
        ):
            service = ContractRadarService()
            first = service.scan({"profile_id": "road_civil_infrastructure"})
            with patch("contract_radar.data.load_procurement_data") as load_data:
                second = service.scan(
                    {
                        "profile_id": "road_civil_infrastructure",
                        "business_profile": {
                            "profile_id": "road_civil_infrastructure",
                            "name": "Variant Civil Works",
                            "max_contract_value": 900000,
                            "active_pursuit_count": 0,
                        },
                    }
                )

        load_data.assert_not_called()
        self.assertFalse(first["metrics"].get("scan_result_cache_hit", False))
        self.assertFalse(second["metrics"].get("scan_result_cache_hit", False))
        self.assertEqual(second["business_profile"]["name"], "Variant Civil Works")

    def test_listing_briefs_are_limited_to_contract_inbox(self) -> None:
        captured_document_numbers: list[str] = []

        def passthrough_briefs(profile, opportunities):
            captured_document_numbers.extend(
                item.solicitation.document_number for item in opportunities
            )
            return opportunities, "deterministic_fallback", {
                "opportunity_count": len(opportunities),
                "shortlisted_for_model": len(opportunities),
                "model_calls_attempted": 0,
                "model_calls_successful": 0,
                "model_calls_failed": 0,
                "briefs_generated": 0,
                "label_changes_after_extraction": 0,
                "model_calls_avoided_by_preflight": len(opportunities),
                "model_calls_avoided_by_failure": 0,
                "listing_extraction_cache_hits": 0,
                "model_latency_ms": 0,
                "nim_preflight": {"available": False, "reason": "test"},
            }

        with patch.dict(
            os.environ,
            {
                "CONTRACT_RADAR_OFFLINE": "1",
                "CONTRACT_RADAR_DISABLE_NEMOTRON": "1",
            },
            clear=False,
        ):
            service = ContractRadarService()
            with patch(
                "contract_radar.nemotron.enrich_top_opportunities_with_stats",
                side_effect=passthrough_briefs,
            ):
                scan = service.scan({"profile_id": "road_civil_infrastructure"})

        inbox_document_numbers = [
            item["solicitation"]["document_number"]
            for item in [*scan["top_opportunities"], *scan["watchlist"]]
        ]
        skipped_document_numbers = {
            item["solicitation"]["document_number"] for item in scan["skipped"]
        }

        self.assertEqual(captured_document_numbers, inbox_document_numbers)
        self.assertLessEqual(len(captured_document_numbers), 13)
        self.assertFalse(set(captured_document_numbers) & skipped_document_numbers)


if __name__ == "__main__":
    unittest.main()
