from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from contract_radar import config


def precomputed_scan_path(profile_id: str, priority_mode: str, as_of: date | None) -> Path:
    scan_dir = config.PRECOMPUTED_DIR / "scans"
    filename = _scan_filename(profile_id, priority_mode, as_of)
    return scan_dir / filename


def precomputed_latest_scan_path(profile_id: str, priority_mode: str) -> Path:
    scan_dir = config.PRECOMPUTED_DIR / "scans"
    filename = _scan_filename(profile_id, priority_mode, None)
    return scan_dir / filename


def load_precomputed_scan(profile_id: str, priority_mode: str, as_of: date | None) -> dict[str, Any] | None:
    if not config.env_flag(config.USE_PRECOMPUTED_SCAN_ENV):
        return None

    candidates = []
    if as_of is not None:
        candidates.append(precomputed_scan_path(profile_id, priority_mode, as_of))
    candidates.append(precomputed_latest_scan_path(profile_id, priority_mode))

    for path in candidates:
        payload = _read_json(path)
        if payload is None:
            continue
        result = copy.deepcopy(payload)
        metrics = result.setdefault("metrics", {})
        warnings = metrics.setdefault("warnings", [])
        if isinstance(warnings, list):
            warnings.append(f"Precomputed scan replay loaded from {path}.")
        metrics["precomputed_scan_replay"] = True
        result["precomputed_scan_path"] = str(path)
        return result
    return None


def write_precomputed_scan(
    scan_result: dict[str, Any],
    profile_id: str,
    priority_mode: str,
    as_of: date | None,
) -> list[Path]:
    dated_path = precomputed_scan_path(profile_id, priority_mode, as_of)
    latest_path = precomputed_latest_scan_path(profile_id, priority_mode)
    dated_path.parent.mkdir(parents=True, exist_ok=True)
    payload = copy.deepcopy(scan_result)
    _strip_runtime_replay_fields(payload)
    body = json.dumps(payload, indent=2, default=str)
    dated_path.write_text(body + "\n", encoding="utf-8")
    if latest_path != dated_path:
        latest_path.write_text(body + "\n", encoding="utf-8")
    return [dated_path, latest_path] if latest_path != dated_path else [dated_path]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _scan_filename(profile_id: str, priority_mode: str, as_of: date | None) -> str:
    date_part = as_of.isoformat() if as_of else "latest"
    return f"{_slug(profile_id)}__{_slug(priority_mode)}__{date_part}.json"


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower())
    return text.strip("-") or "default"


def _strip_runtime_replay_fields(payload: dict[str, Any]) -> None:
    payload.pop("precomputed_scan_path", None)
    metrics = payload.get("metrics")
    if isinstance(metrics, dict):
        metrics.pop("precomputed_scan_replay", None)
        warnings = metrics.get("warnings")
        if isinstance(warnings, list):
            metrics["warnings"] = [
                warning
                for warning in warnings
                if "Precomputed scan replay loaded from" not in str(warning)
            ]
