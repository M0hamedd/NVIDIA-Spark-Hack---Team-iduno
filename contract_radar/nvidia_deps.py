from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from importlib import util
from typing import Any, Callable

from contract_radar import config


AUTO_INSTALL_CUOPT_ENV = "CONTRACT_RADAR_AUTO_INSTALL_CUOPT"
CUOPT_PACKAGE_ENV = "CONTRACT_RADAR_CUOPT_PACKAGE"
CUDA_MAJOR_ENV = "CONTRACT_RADAR_CUDA_MAJOR"
CUOPT_VERSION_ENV = "CONTRACT_RADAR_CUOPT_VERSION"
NVIDIA_PIP_INDEX = "https://pypi.nvidia.com"
DEFAULT_CUOPT_VERSION = "26.4.*"


def ensure_spark_cuopt(
    *,
    enabled: bool = True,
    print_fn: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Best-effort cuOpt bootstrap for DGX Spark demos.

    The app can run without cuOpt, so failed installs are reported and the
    deterministic portfolio optimizer remains available.
    """

    if not enabled or not config.env_flag(AUTO_INSTALL_CUOPT_ENV, default=True):
        return {"status": "skipped", "reason": "auto_install_disabled"}
    if _cuopt_api_available():
        return {"status": "available", "package": "cuopt"}
    if platform.system() != "Linux":
        return {"status": "skipped", "reason": "not_linux"}
    if shutil.which("nvidia-smi") is None:
        return {"status": "skipped", "reason": "nvidia_smi_not_found"}

    package = _cuopt_package()
    spec = f"{package}=={os.getenv(CUOPT_VERSION_ENV, DEFAULT_CUOPT_VERSION)}"
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--extra-index-url",
        NVIDIA_PIP_INDEX,
        spec,
    ]
    print_fn(f"cuOpt is not active; installing {spec} from NVIDIA's Python index.")
    try:
        subprocess.check_call(command)
    except (subprocess.CalledProcessError, OSError) as exc:
        print_fn(f"cuOpt install failed; continuing with greedy fallback ({exc}).")
        return {"status": "failed", "package": package, "error": str(exc)}

    if _cuopt_api_available():
        print_fn("cuOpt install complete; portfolio optimizer will use cuOpt MILP.")
        return {"status": "installed", "package": package}

    print_fn("cuOpt package installed, but the expected Python MILP API was not importable.")
    return {
        "status": "failed",
        "package": package,
        "error": "cuopt_milp_api_unavailable_after_install",
    }


def _cuopt_api_available() -> bool:
    if util.find_spec("cuopt") is None:
        return False
    try:
        from cuopt.linear_programming.problem import INTEGER, MAXIMIZE, Problem
        from cuopt.linear_programming.solver_settings import SolverSettings

        return all((Problem, INTEGER, MAXIMIZE, SolverSettings))
    except Exception:
        return False


def _cuopt_package() -> str:
    explicit = os.getenv(CUOPT_PACKAGE_ENV, "").strip()
    if explicit:
        return explicit
    cuda_major = _cuda_major()
    if cuda_major == "12":
        return "cuopt-cu12"
    return "cuopt-cu13"


def _cuda_major() -> str:
    explicit = os.getenv(CUDA_MAJOR_ENV, "").strip()
    if explicit in {"12", "13"}:
        return explicit
    output = _nvidia_smi_output()
    match = re.search(r"CUDA Version:\s*(\d+)", output)
    if match and match.group(1) in {"12", "13"}:
        return match.group(1)
    return "13"


def _nvidia_smi_output() -> str:
    try:
        completed = subprocess.run(
            ["nvidia-smi"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return f"{completed.stdout}\n{completed.stderr}"
