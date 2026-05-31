from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BenchmarkScriptTests(unittest.TestCase):
    def test_offline_benchmark_reports_scorecard_and_model_efficiency(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "benchmark_pipeline.py"),
                "--offline",
                "--profile",
                "parks_landscape",
                "--repeat",
                "2",
                "--json",
            ],
            cwd=ROOT,
            env=_fallback_env(),
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(payload["repeat"], 2)
        self.assertEqual(payload["profile"]["profile_id"], "parks_landscape")
        self.assertGreater(payload["average_records_per_second"], 0)
        self.assertEqual(
            payload["local_record_replay"]["total_local_records_processed"],
            payload["last_scan"]["solicitations_loaded"] + payload["last_scan"]["awards_loaded"],
        )
        self.assertGreater(payload["local_record_replay"]["records_per_second"], 0)
        self.assertIn("data_source_statuses", payload["local_record_replay"])
        self.assertIn("data_source_statuses", payload["last_scan"])
        self.assertIn("shortlist_reduction_percent", payload["performance_proof"])
        self.assertIn("active_nvidia_path", payload["performance_proof"])
        self.assertGreaterEqual(payload["last_scan"]["model_calls_avoided"], 1)
        self.assertIn("model_calls_successful", payload["last_scan"])
        self.assertIn("briefs_generated", payload["last_scan"])
        self.assertIn("label_changes_after_extraction", payload["last_scan"])
        self.assertEqual(
            payload["performance_proof"]["model_calls_avoided"],
            payload["last_scan"]["model_calls_avoided"],
        )
        self.assertEqual(
            payload["performance_proof"]["briefs_generated"],
            payload["last_scan"]["briefs_generated"],
        )
        self.assertIn(payload["last_scan"]["nemotron_mode"], {"deterministic_fallback", "local_nim"})
        self.assertGreaterEqual(payload["insight_scorecard"]["false_positives_skipped"], 1)
        self.assertTrue(payload["insight_scorecard"]["best_current_opportunity"]["document_number"])
        self.assertTrue(payload["insight_scorecard"]["buyer_division_pattern"])
        self.assertTrue(payload["insight_scorecard"]["similar_award_range"])
        self.assertGreater(len(payload["insight_scorecard"]["similar_award_examples"]), 0)
        self.assertGreater(len(payload["insight_scorecard"]["false_positive_categories"]), 0)
        self.assertIn("top_insight", payload["insight_scorecard"])

    def test_require_nvidia_fails_clearly_in_offline_fallback(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "benchmark_pipeline.py"),
                "--offline",
                "--repeat",
                "1",
                "--require-nvidia",
            ],
            cwd=ROOT,
            env=_fallback_env(),
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )

        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("NVIDIA proof gate failed", completed.stderr)
        self.assertIn("nvidia_stack_active=false", completed.stderr)
        self.assertIn("active_nvidia_tools=[]", completed.stderr)


def _fallback_env() -> dict[str, str]:
    env = dict(os.environ)
    env["CONTRACT_RADAR_OFFLINE"] = "1"
    env["NIM_BASE_URL"] = "http://127.0.0.1:9/v1"
    env["NIM_PREFLIGHT_TIMEOUT_SECONDS"] = "0.05"
    return env


if __name__ == "__main__":
    unittest.main()
