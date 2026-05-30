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
        env = dict(os.environ)
        env["CONTRACT_RADAR_OFFLINE"] = "1"
        env["NIM_BASE_URL"] = "http://127.0.0.1:9/v1"
        env["NIM_PREFLIGHT_TIMEOUT_SECONDS"] = "0.05"

        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "benchmark_pipeline.py"),
                "--offline",
                "--repeat",
                "2",
                "--json",
            ],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        payload = json.loads(completed.stdout)

        self.assertEqual(payload["repeat"], 2)
        self.assertGreater(payload["average_records_per_second"], 0)
        self.assertGreaterEqual(payload["last_scan"]["model_calls_avoided"], 1)
        self.assertIn(payload["last_scan"]["nemotron_mode"], {"deterministic_fallback", "local_nim"})
        self.assertGreaterEqual(payload["insight_scorecard"]["false_positives_skipped"], 1)
        self.assertIn("top_insight", payload["insight_scorecard"])


if __name__ == "__main__":
    unittest.main()
