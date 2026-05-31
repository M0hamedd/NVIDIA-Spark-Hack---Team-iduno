from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.getenv("CONTRACT_RADAR_CACHE_DIR", ROOT_DIR / "data" / "cache"))

OFFLINE_ENV = "CONTRACT_RADAR_OFFLINE"
REFRESH_ENV = "CONTRACT_RADAR_REFRESH"
ROW_LIMIT_ENV = "CONTRACT_RADAR_ROW_LIMIT"
ALLOW_SAMPLE_DATA_ENV = "CONTRACT_RADAR_ALLOW_SAMPLE_DATA"

DEFAULT_ROW_LIMIT = 10000
CKAN_ACTION_BASE_URL = "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action"
CKAN_DATASTORE_SEARCH_URL = f"{CKAN_ACTION_BASE_URL}/datastore_search"
CKAN_DATASTORE_DUMP_URL = f"{CKAN_ACTION_BASE_URL}/datastore_dump"

SOLICITATIONS_RESOURCE_ID = "f676f46c-de76-4e94-bba7-0a3951aa0603"
AWARDED_CONTRACTS_RESOURCE_ID = "e211f003-5909-4bea-bd96-d75899d8e612"

SOLICITATIONS_SOURCE = "Toronto Bids Solicitations"
AWARDED_CONTRACTS_SOURCE = "Toronto Bids Awarded Contracts"

DATASETS = {
    "solicitations": {
        "name": SOLICITATIONS_SOURCE,
        "resource_id": SOLICITATIONS_RESOURCE_ID,
        "cache_file": "toronto_bids_solicitations.json",
    },
    "awards": {
        "name": AWARDED_CONTRACTS_SOURCE,
        "resource_id": AWARDED_CONTRACTS_RESOURCE_ID,
        "cache_file": "toronto_bids_awarded_contracts.json",
    },
}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def row_limit() -> int:
    raw = os.getenv(ROW_LIMIT_ENV, str(DEFAULT_ROW_LIMIT)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_ROW_LIMIT
