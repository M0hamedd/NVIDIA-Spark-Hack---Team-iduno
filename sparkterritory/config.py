from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.getenv("SPARKTERRITORY_CACHE_DIR", ROOT_DIR / "data" / "cache"))
ROW_LIMIT = int(os.getenv("SPARKTERRITORY_ROW_LIMIT", "0") or "0")
REFRESH_CACHE = os.getenv("SPARKTERRITORY_REFRESH", "0") == "1"
OFFLINE_MODE = os.getenv("SPARKTERRITORY_OFFLINE", "0") == "1"

CKAN_DUMP_BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca/datastore/dump"

DATASETS = {
    "active_permits": {
        "title": "Building Permits - Active Permits",
        "package": "building-permits-active-permits",
        "resource_id": "6d0229af-bc54-46de-9c2b-26759b01dd05",
        "filename": "building-permits-active-permits.csv",
    },
    "cleared_permits": {
        "title": "Building Permits - Cleared Permits",
        "package": "building-permits-cleared-permits",
        "resource_id": "a96c0ba4-3026-402b-b09d-5b1268b8f810",
        "filename": "building-permits-cleared-permits.csv",
    },
    "development_pipeline": {
        "title": "Development Pipeline",
        "package": "development-pipeline",
        "resource_id": "7aad5dbd-a769-4bd5-b5d2-f9bb605b6bf9",
        "filename": "development-pipeline.csv",
    },
    "neighbourhood_profiles": {
        "title": "Neighbourhood Profiles 2016 - 140 Model",
        "package": "neighbourhood-profiles",
        "resource_id": "7f8eee5e-85fb-415c-aef3-c3bd4998445f",
        "filename": "neighbourhood-profiles-2016-140-model.csv",
    },
    "neighbourhoods": {
        "title": "Neighbourhoods - historical 140",
        "package": "neighbourhoods",
        "resource_id": "7d3ae06b-0217-4cc9-92ed-97adafca2f7b",
        "filename": "neighbourhoods-historical-140.geojson.csv",
    },
}

SCORE_WEIGHTS = {
    "current_demand_score": 0.35,
    "future_growth_score": 0.25,
    "customer_fit_score": 0.20,
    "growth_momentum_score": 0.10,
    "operational_feasibility_score": 0.10,
}

NIM_BASE_URL = os.getenv("NIM_BASE_URL", "http://localhost:8000/v1").rstrip("/")
NIM_MODEL = os.getenv("NIM_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")
NIM_API_KEY = os.getenv("NIM_API_KEY", "")
