from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from contract_radar import config
from contract_radar.models import AwardRecord, Solicitation
from contract_radar.sample_data import sample_awards, sample_solicitations


@dataclass
class ProcurementDataBundle:
    solicitations: list[Solicitation]
    awards: list[AwardRecord]
    source_status: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    fetched_at: str = ""
    engine: str = "python_stdlib"
    rapids_mode: str = "python_fallback"


def load_procurement_data(refresh: bool = False) -> ProcurementDataBundle:
    fetched_at = _utc_now()
    warnings: list[str] = []
    source_status: dict[str, str] = {}
    engine = "python_stdlib"
    rapids_mode = "python_fallback"

    if config.env_flag(config.OFFLINE_ENV):
        solicitations = sample_solicitations()
        awards = sample_awards()
        if _rapids_available():
            engine = "rapids_cudf"
            rapids_mode = "rapids_available_sample_bypassed"
        return ProcurementDataBundle(
            solicitations=solicitations,
            awards=awards,
            source_status={
                config.SOLICITATIONS_SOURCE: f"fallback_sample ({len(solicitations)} records)",
                config.AWARDED_CONTRACTS_SOURCE: f"fallback_sample ({len(awards)} records)",
            },
            warnings=[f"{config.OFFLINE_ENV}=true; using sample data"],
            fetched_at=fetched_at,
            engine=engine,
            rapids_mode=rapids_mode,
        )

    effective_refresh = refresh or config.env_flag(config.REFRESH_ENV)
    limit = config.row_limit()

    solicitation_records, solicitation_rapids_mode = _load_records(
        dataset_key="solicitations",
        refresh=effective_refresh,
        limit=limit,
        source_status=source_status,
        warnings=warnings,
    )
    award_records, award_rapids_mode = _load_records(
        dataset_key="awards",
        refresh=effective_refresh,
        limit=limit,
        source_status=source_status,
        warnings=warnings,
    )
    if "rapids_cudf" in {solicitation_rapids_mode, award_rapids_mode}:
        engine = "rapids_cudf"
        rapids_mode = "rapids_cudf"

    if solicitation_records is None or award_records is None:
        solicitations = sample_solicitations()
        awards = sample_awards()
        source_status[config.SOLICITATIONS_SOURCE] = f"fallback_sample ({len(solicitations)} records)"
        source_status[config.AWARDED_CONTRACTS_SOURCE] = f"fallback_sample ({len(awards)} records)"
        warnings.append("Live/cache procurement data incomplete; using sample data bundle")
    else:
        solicitations = [Solicitation.from_record(record) for record in solicitation_records]
        awards = [AwardRecord.from_record(record) for record in award_records]

    return ProcurementDataBundle(
        solicitations=solicitations,
        awards=awards,
        source_status=source_status,
        warnings=warnings,
        fetched_at=fetched_at,
        engine=engine,
        rapids_mode=rapids_mode,
    )


def _load_records(
    dataset_key: str,
    refresh: bool,
    limit: int,
    source_status: dict[str, str],
    warnings: list[str],
) -> tuple[list[dict[str, Any]] | None, str]:
    dataset = config.DATASETS[dataset_key]
    source_name = str(dataset["name"])
    cache_path = config.CACHE_DIR / str(dataset["cache_file"])

    if not refresh:
        cached = _read_cache(cache_path)
        if cached is not None:
            source_status[source_name] = f"cache ({len(cached)} records)"
            return _prepare_records(dataset_key, cached, limit, warnings)

    try:
        records = _fetch_datastore_search(str(dataset["resource_id"]), limit)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        warnings.append(f"{source_name}: live fetch failed ({exc})")
        cached = _read_cache(cache_path)
        if cached is not None:
            source_status[source_name] = f"cache_after_live_failure ({len(cached)} records)"
            return _prepare_records(dataset_key, cached, limit, warnings)
        return None, "python_fallback"

    _write_cache(cache_path, records)
    source_status[source_name] = f"live ({len(records)} records)"
    return _prepare_records(dataset_key, records, limit, warnings)


def _fetch_datastore_search(resource_id: str, limit: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    offset = 0
    page_size = min(1000, limit)

    while len(records) < limit:
        params = urlencode({"resource_id": resource_id, "limit": page_size, "offset": offset})
        with urlopen(f"{config.CKAN_DATASTORE_SEARCH_URL}?{params}", timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if not payload.get("success"):
            raise ValueError("CKAN datastore_search returned success=false")

        result = payload.get("result") or {}
        page = result.get("records") or []
        if not isinstance(page, list):
            raise ValueError("CKAN datastore_search records payload was not a list")

        records.extend([record for record in page if isinstance(record, dict)])
        total = int(result.get("total") or 0)
        if not page or len(records) >= total:
            break
        offset += len(page)

    return records[:limit]


def _read_cache(path: Path) -> list[dict[str, Any]] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return None
    return [record for record in records if isinstance(record, dict)]


def _write_cache(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": _utc_now(),
        "records": records,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _prepare_records(
    dataset_key: str,
    records: list[dict[str, Any]],
    limit: int,
    warnings: list[str],
) -> tuple[list[dict[str, Any]], str]:
    """Use RAPIDS/cuDF for the first local validity filter when available."""

    limited = records[:limit]
    if not _rapids_available() or not limited:
        return limited, "python_fallback"

    try:
        import cudf  # type: ignore[import-not-found]

        dataframe = cudf.DataFrame(limited)
        id_column = _first_existing_column(dataframe, ("Document Number", "document_number"))
        description_column = _first_existing_column(
            dataframe,
            ("Solicitation Document Description", "description"),
        )
        if id_column:
            id_values = dataframe[id_column].fillna("").astype("str")
            dataframe = dataframe[id_values.str.len() > 0]
        if description_column:
            description_values = dataframe[description_column].fillna("").astype("str")
            dataframe = dataframe[description_values.str.len() > 0]
        prepared = dataframe.head(limit).to_pandas()
        prepared = prepared.where(prepared.notna(), None)
        return prepared.to_dict("records"), "rapids_cudf"
    except Exception as exc:
        warnings.append(f"RAPIDS/cuDF filtering failed for {dataset_key}; using python fallback ({exc})")
        return limited, "python_fallback"


def _first_existing_column(dataframe: Any, candidates: tuple[str, ...]) -> str:
    columns = set(str(column) for column in getattr(dataframe, "columns", []))
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return ""


def _rapids_available() -> bool:
    try:
        __import__("cudf")
    except Exception:
        return False
    return True


def _engine_label() -> str:
    return "rapids_cudf" if _rapids_available() else "python_stdlib"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
