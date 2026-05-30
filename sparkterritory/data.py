from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sparkterritory.config import CACHE_DIR, CKAN_DUMP_BASE, DATASETS, OFFLINE_MODE, REFRESH_CACHE, ROW_LIMIT
from sparkterritory.geo import district_from_fsa, district_from_neighbourhood, district_from_ward
from sparkterritory.samples import (
    SAMPLE_CURRENT_BY_DISTRICT,
    SAMPLE_FUTURE_BY_DISTRICT,
    SAMPLE_GROWTH_BY_DISTRICT,
    SAMPLE_NEIGHBOURHOODS,
)
from sparkterritory.utils import log_signal, normalize_name, safe_divide, to_number


PROFILE_CHARACTERISTICS = {
    "number": "Neighbourhood Number",
    "population": "Population, 2016",
    "density": "Population density per square kilometre",
    "dwellings": "Total private dwellings",
    "highrise_apartments": "  Apartment in a building that has five or more storeys",
    "avg_income": "Total income: Average amount ($)",
}

WINDOW_WASHING_TERMS = (
    "apartment",
    "condo",
    "condomin",
    "multi",
    "residential",
    "mixed",
    "townhouse",
    "hotel",
    "office",
    "commercial",
)


@dataclass
class DataSignals:
    neighbourhoods: dict[str, dict[str, float | str]]
    current_by_district: dict[str, dict[str, float]]
    growth_by_district: dict[str, dict[str, float]]
    future_by_district: dict[str, dict[str, float]]
    source_status: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    dataframe_engine: str = "python_csv_fallback"


def cudf_available() -> bool:
    try:
        import cudf  # noqa: F401

        return True
    except Exception:
        return False


def dataframe_engine_label() -> str:
    return "rapids_cudf" if cudf_available() else "python_csv_fallback"


def ensure_dataset(dataset_key: str, refresh: bool = False) -> Path:
    dataset = DATASETS[dataset_key]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    target = CACHE_DIR / _cache_filename(dataset["filename"])
    if target.exists() and not refresh:
        return target

    fd, temp_name = tempfile.mkstemp(prefix=f"{dataset_key}-", suffix=".csv")
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        if ROW_LIMIT:
            _download_sample(dataset["resource_id"], temp_path)
        else:
            url = f"{CKAN_DUMP_BASE}/{dataset['resource_id']}"
            with urllib.request.urlopen(url, timeout=120) as response:
                with temp_path.open("wb") as output:
                    shutil.copyfileobj(response, output)
        temp_path.replace(target)
        return target
    except (urllib.error.URLError, TimeoutError, OSError):
        if temp_path.exists():
            temp_path.unlink()
        raise


def _cache_filename(filename: str) -> str:
    if ROW_LIMIT:
        return f"sample-{ROW_LIMIT}-{filename}"
    return filename


def _download_sample(resource_id: str, target: Path) -> None:
    url = (
        "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/datastore_search"
        f"?resource_id={resource_id}&limit={ROW_LIMIT}"
    )
    with urllib.request.urlopen(url, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    records = payload.get("result", {}).get("records", [])
    field_names = [field["id"] for field in payload.get("result", {}).get("fields", [])]
    if not field_names and records:
        field_names = list(records[0].keys())
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=field_names, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def load_signals(refresh: bool = REFRESH_CACHE) -> DataSignals:
    source_status: dict[str, str] = {}
    warnings: list[str] = []
    paths: dict[str, Path] = {}

    for key in DATASETS:
        if OFFLINE_MODE:
            source_status[key] = "embedded_fallback_offline_mode"
            continue
        try:
            paths[key] = ensure_dataset(key, refresh=refresh)
            source_status[key] = f"cached_live_open_data_sample_{ROW_LIMIT}" if ROW_LIMIT else "cached_live_open_data_full"
        except Exception as exc:
            source_status[key] = "embedded_fallback"
            warnings.append(f"{DATASETS[key]['title']} unavailable, using embedded fallback where needed: {exc}")

    if OFFLINE_MODE:
        warnings.append("SPARKTERRITORY_OFFLINE=1 is set. Using embedded data for a fast local smoke test.")

    engine = dataframe_engine_label()
    if engine == "rapids_cudf":
        warnings.append("RAPIDS/cuDF detected. DGX Spark data engine is available.")
    else:
        warnings.append("RAPIDS/cuDF not detected. Running stdlib CSV fallback for local development.")

    neighbourhoods = (
        load_neighbourhood_profiles(paths["neighbourhood_profiles"])
        if "neighbourhood_profiles" in paths
        else dict(SAMPLE_NEIGHBOURHOODS)
    )
    current_by_district = (
        aggregate_permits(paths["active_permits"])
        if "active_permits" in paths
        else dict(SAMPLE_CURRENT_BY_DISTRICT)
    )
    growth_by_district = (
        aggregate_permits(paths["cleared_permits"])
        if "cleared_permits" in paths
        else dict(SAMPLE_GROWTH_BY_DISTRICT)
    )
    future_by_district = (
        aggregate_development(paths["development_pipeline"])
        if "development_pipeline" in paths
        else dict(SAMPLE_FUTURE_BY_DISTRICT)
    )

    if not neighbourhoods:
        neighbourhoods = dict(SAMPLE_NEIGHBOURHOODS)
        warnings.append("Neighbourhood profile parsing returned no records; using embedded profile fallback.")
    if not current_by_district:
        current_by_district = dict(SAMPLE_CURRENT_BY_DISTRICT)
        warnings.append("Active permit aggregation returned no records; using embedded active permit fallback.")
    if not growth_by_district:
        growth_by_district = dict(SAMPLE_GROWTH_BY_DISTRICT)
        warnings.append("Cleared permit aggregation returned no records; using embedded cleared permit fallback.")
    if not future_by_district:
        future_by_district = dict(SAMPLE_FUTURE_BY_DISTRICT)
        warnings.append("Development aggregation returned no records; using embedded development fallback.")

    return DataSignals(
        neighbourhoods=neighbourhoods,
        current_by_district=current_by_district,
        growth_by_district=growth_by_district,
        future_by_district=future_by_district,
        source_status=source_status,
        warnings=warnings,
        dataframe_engine=engine,
    )


def load_neighbourhood_profiles(path: Path) -> dict[str, dict[str, float | str]]:
    wanted = set(PROFILE_CHARACTERISTICS.values())
    rows_by_characteristic: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in _limited(reader):
            characteristic = row.get("Characteristic", "")
            if characteristic in wanted:
                rows_by_characteristic[characteristic] = row

    number_row = rows_by_characteristic.get(PROFILE_CHARACTERISTICS["number"], {})
    neighbourhood_columns = [
        column
        for column in number_row
        if column
        not in {
            "_id",
            "Category",
            "Topic",
            "Data Source",
            "Characteristic",
            "City of Toronto",
        }
    ]

    neighbourhoods: dict[str, dict[str, float | str]] = {}
    for name in neighbourhood_columns:
        number = to_number(number_row.get(name))
        dwellings = _profile_value(rows_by_characteristic, "dwellings", name)
        highrise = _profile_value(rows_by_characteristic, "highrise_apartments", name)
        density = _profile_value(rows_by_characteristic, "density", name)
        income = _profile_value(rows_by_characteristic, "avg_income", name)
        population = _profile_value(rows_by_characteristic, "population", name)
        neighbourhoods[name] = {
            "number": number,
            "district": district_from_neighbourhood(name, number),
            "population": population,
            "density": density,
            "dwellings": dwellings,
            "highrise_apartments": highrise,
            "highrise_share": safe_divide(highrise, dwellings),
            "avg_income": income,
        }
    return neighbourhoods


def aggregate_permits(path: Path) -> dict[str, dict[str, float]]:
    if cudf_available():
        try:
            return _aggregate_permits_cudf(path)
        except Exception:
            return _aggregate_permits_csv(path)
    return _aggregate_permits_csv(path)


def aggregate_development(path: Path) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in _limited(reader):
            district = district_from_ward(row.get("Ward"))
            if district == "Unknown":
                continue
            residential_units = to_number(row.get("Proposed Residential Units"))
            residential_gfa = to_number(row.get("Proposed Residential Gross Floor Area"))
            nonres_gfa = to_number(row.get("Proposed Non-Residential Gross Floor Area"))
            gross_floor_area = to_number(row.get("Proposed Gross Floor Area")) or residential_gfa + nonres_gfa
            bucket = totals.setdefault(
                district,
                {"applications": 0.0, "residential_units": 0.0, "gross_floor_area": 0.0, "weighted_value": 0.0},
            )
            bucket["applications"] += 1.0
            bucket["residential_units"] += residential_units
            bucket["gross_floor_area"] += gross_floor_area
            bucket["weighted_value"] += 1.0 + log_signal(residential_units) + log_signal(gross_floor_area / 1000.0)
    return totals


def _aggregate_permits_csv(path: Path) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in _limited(reader):
            district = district_from_fsa(row.get("POSTAL"))
            if district == "Unknown" or district == "Mississauga":
                continue
            relevance_text = " ".join(
                str(row.get(column, ""))
                for column in ("STRUCTURE_TYPE", "PROPOSED_USE", "CURRENT_USE", "DESCRIPTION", "PERMIT_TYPE", "WORK")
            ).lower()
            if not any(term in relevance_text for term in WINDOW_WASHING_TERMS):
                continue
            cost = to_number(row.get("EST_CONST_COST"))
            units = max(0.0, to_number(row.get("DWELLING_UNITS_CREATED")))
            bucket = totals.setdefault(
                district,
                {"records": 0.0, "weighted_value": 0.0, "cost": 0.0, "units": 0.0},
            )
            bucket["records"] += 1.0
            bucket["cost"] += cost
            bucket["units"] += units
            bucket["weighted_value"] += 1.0 + log_signal(cost / 100000.0) + log_signal(units)
    return totals


def _aggregate_permits_cudf(path: Path) -> dict[str, dict[str, float]]:
    import cudf

    df = cudf.read_csv(str(path), dtype=str)
    for column in ("POSTAL", "STRUCTURE_TYPE", "PROPOSED_USE", "CURRENT_USE", "DESCRIPTION", "PERMIT_TYPE", "WORK"):
        if column not in df.columns:
            df[column] = ""
    text = (
        df["STRUCTURE_TYPE"].fillna("")
        + " "
        + df["PROPOSED_USE"].fillna("")
        + " "
        + df["CURRENT_USE"].fillna("")
        + " "
        + df["DESCRIPTION"].fillna("")
        + " "
        + df["PERMIT_TYPE"].fillna("")
        + " "
        + df["WORK"].fillna("")
    ).str.lower()
    pattern = "|".join(WINDOW_WASHING_TERMS)
    df = df[text.str.contains(pattern, regex=True)]
    df["district"] = df["POSTAL"].fillna("").str.strip().str.upper().str.slice(0, 2)
    df = df[df["district"].isin(["M1", "M2", "M3", "M4", "M5", "M6", "M8", "M9"])]
    district_map = {
        "M1": "Scarborough",
        "M2": "North York",
        "M3": "North York",
        "M4": "East York",
        "M5": "Downtown",
        "M6": "West Toronto",
        "M8": "Etobicoke",
        "M9": "Etobicoke",
    }
    df["cost"] = cudf.to_numeric(df.get("EST_CONST_COST", 0), errors="coerce").fillna(0)
    df["units"] = cudf.to_numeric(df.get("DWELLING_UNITS_CREATED", 0), errors="coerce").fillna(0)
    df["record"] = 1.0
    df["weighted_value"] = 1.0 + (df["cost"].clip(0, 5000000) / 5000000) + (df["units"].clip(0, 500) / 100)
    grouped = df.groupby("district").agg(
        {"record": "sum", "weighted_value": "sum", "cost": "sum", "units": "sum"}
    )
    result: dict[str, dict[str, float]] = {}
    records = grouped.to_pandas().reset_index().to_dict("records")
    for row in records:
        result[district_map[row["district"]]] = {
            "records": float(row["record"]),
            "weighted_value": float(row["weighted_value"]),
            "cost": float(row["cost"]),
            "units": float(row["units"]),
        }
    return result


def _profile_value(rows_by_characteristic: dict[str, dict[str, Any]], key: str, name: str) -> float:
    characteristic = PROFILE_CHARACTERISTICS[key]
    return to_number(rows_by_characteristic.get(characteristic, {}).get(name))


def _limited(reader: csv.DictReader) -> Any:
    for index, row in enumerate(reader):
        if ROW_LIMIT and index >= ROW_LIMIT:
            break
        yield row
