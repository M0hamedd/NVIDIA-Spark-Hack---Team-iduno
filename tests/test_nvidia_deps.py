from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from contract_radar.nvidia_deps import ensure_spark_cuopt


class NvidiaDependencyBootstrapTests(unittest.TestCase):
    def test_skips_when_auto_install_is_disabled(self) -> None:
        with patch.dict(os.environ, {"CONTRACT_RADAR_AUTO_INSTALL_CUOPT": "0"}, clear=False):
            result = ensure_spark_cuopt(print_fn=lambda _: None)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "auto_install_disabled")

    def test_skips_on_non_linux_without_installing(self) -> None:
        with patch("contract_radar.nvidia_deps._cuopt_api_available", return_value=False):
            with patch("contract_radar.nvidia_deps.platform.system", return_value="Windows"):
                with patch("contract_radar.nvidia_deps.subprocess.check_call") as check_call:
                    result = ensure_spark_cuopt(print_fn=lambda _: None)

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "not_linux")
        check_call.assert_not_called()

    def test_installs_matching_cuda_package_on_linux_gpu_host(self) -> None:
        messages: list[str] = []
        check_call = Mock()
        availability = [False, True]

        with patch("contract_radar.nvidia_deps._cuopt_api_available", side_effect=lambda: availability.pop(0)):
            with patch("contract_radar.nvidia_deps.platform.system", return_value="Linux"):
                with patch("contract_radar.nvidia_deps.shutil.which", return_value="/usr/bin/nvidia-smi"):
                    with patch("contract_radar.nvidia_deps._cuda_major", return_value="12"):
                        with patch("contract_radar.nvidia_deps.subprocess.check_call", check_call):
                            result = ensure_spark_cuopt(print_fn=messages.append)

        self.assertEqual(result["status"], "installed")
        self.assertEqual(result["package"], "cuopt-cu12")
        command = check_call.call_args.args[0]
        self.assertIn("cuopt-cu12==26.4.*", command)
        self.assertIn("https://pypi.nvidia.com", command)
        self.assertTrue(any("installing cuopt-cu12" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
