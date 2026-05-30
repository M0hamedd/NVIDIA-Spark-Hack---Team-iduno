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
        self.assertIn("spark_story", health)

        metrics = scan["metrics"]
        self.assertGreater(metrics["records_per_second"], 0)
        self.assertGreaterEqual(metrics["shortlist_reduction_ratio"], 0)
        self.assertGreaterEqual(metrics["model_calls_avoided"], 1)
        self.assertIn("rapids_mode", metrics)
        self.assertIn("nvidia_stack_active", metrics)
        self.assertIn("insight_scorecard", scan)
        self.assertGreaterEqual(scan["insight_scorecard"]["false_positives_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
