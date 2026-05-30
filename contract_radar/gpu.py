from __future__ import annotations

from importlib import metadata, util
from typing import Any


def gpu_status() -> dict[str, Any]:
    """Report whether RAPIDS/cuDF is available without requiring it."""

    cudf_spec = util.find_spec("cudf")
    rapids_available = cudf_spec is not None
    version = ""
    if rapids_available:
        try:
            version = metadata.version("cudf")
        except metadata.PackageNotFoundError:
            version = "available"

    engine = "rapids_cudf" if rapids_available else "python_stdlib"
    rapids_mode = "rapids_cudf_available" if rapids_available else "python_fallback"
    if rapids_available:
        spark_story = (
            "DGX Spark can use RAPIDS/cuDF for local procurement record filtering "
            "before Nemotron analyzes only the best candidates."
        )
    else:
        spark_story = (
            "RAPIDS/cuDF is not installed in this environment, so V1 uses the "
            "stdlib path while preserving the DGX Spark acceleration hook."
        )

    return {
        "rapids_cudf_available": rapids_available,
        "engine": engine,
        "rapids_mode": rapids_mode,
        "cudf_version": version,
        "nvidia_stack_active": rapids_available,
        "active_nvidia_tools": ["RAPIDS/cuDF"] if rapids_available else [],
        "spark_story": spark_story,
    }
