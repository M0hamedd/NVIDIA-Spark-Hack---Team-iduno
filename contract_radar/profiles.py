from __future__ import annotations

from copy import deepcopy
from typing import Any

from contract_radar.models import BusinessProfile


SUPPORTED_PROFILE_IDS = (
    "design_engineering",
    "parks_landscape",
    "building_mechanical",
)


SUPPORTED_PROFILE_PAYLOADS: dict[str, dict[str, Any]] = {
    "design_engineering": {
        "profile_id": "design_engineering",
        "name": "CivicWorks Design Studio",
        "business_type": "municipal design, engineering, planning, and contract administration firm",
        "base_location": "Toronto, GTA",
        "team_size": 15,
        "max_contract_value": 900000,
        "max_sites_per_day": 3,
        "active_pursuit_count": 2,
        "max_active_pursuits": 4,
        "service_area": "Toronto",
        "skills": [
            "professional consulting engineering services",
            "preliminary design",
            "detailed design",
            "construction contract administration",
            "construction inspection",
            "municipal planning studies",
            "park and public realm design",
            "accessibility upgrades",
            "facility condition assessments",
            "geotechnical coordination",
            "environmental assessment support",
        ],
        "ready_documents": [
            "insurance",
            "WSIB",
            "HST",
            "professional references",
            "licensed engineer roster",
        ],
        "missing_capabilities": [
            "construction services",
            "general contractor",
            "road paving",
            "pavement markings",
            "supply and custom application",
            "landscaping construction",
            "locksmith",
            "door hardware",
            "kitchen smallwares",
            "HVAC maintenance",
            "food supply",
            "software implementation",
        ],
        "response_days_available": 14,
    },
    "parks_landscape": {
        "profile_id": "parks_landscape",
        "name": "Greenline Parks & Landscape Ltd.",
        "business_type": "parks, playground, landscaping, arborist, and public realm contractor",
        "base_location": "Toronto, GTA",
        "team_size": 16,
        "max_contract_value": 650000,
        "max_sites_per_day": 6,
        "active_pursuit_count": 1,
        "max_active_pursuits": 3,
        "service_area": "Toronto",
        "skills": [
            "park improvements",
            "playground installation",
            "splash pad repairs",
            "landscaping",
            "tree and arborist services",
            "trail repairs",
            "sports field maintenance",
            "topsoil supply",
            "planting",
            "site furnishings",
            "fencing",
            "public realm maintenance",
        ],
        "ready_documents": [
            "insurance",
            "WSIB",
            "HST",
            "references",
            "arborist certificates",
        ],
        "missing_capabilities": [
            "professional engineering services",
            "architectural design",
            "major road construction",
            "watermain replacement",
            "sewer rehabilitation",
            "software implementation",
            "food supply",
        ],
        "response_days_available": 12,
    },
    "building_mechanical": {
        "profile_id": "building_mechanical",
        "name": "GTA Mechanical & Building Services Ltd.",
        "business_type": "municipal building maintenance, HVAC, plumbing, doors, washrooms, and mechanical services contractor",
        "base_location": "Toronto, GTA",
        "team_size": 18,
        "max_contract_value": 750000,
        "max_sites_per_day": 8,
        "active_pursuit_count": 2,
        "max_active_pursuits": 3,
        "service_area": "Toronto",
        "skills": [
            "HVAC maintenance",
            "building automation systems",
            "BAS controls",
            "boiler service",
            "chiller service",
            "plumbing repairs",
            "door hardware services",
            "washroom repairs",
            "preventative maintenance",
            "emergency repair",
            "municipal facility service",
            "small building repairs",
        ],
        "ready_documents": [
            "insurance",
            "WSIB",
            "HST",
            "references",
            "technician certifications",
        ],
        "missing_capabilities": [
            "road paving",
            "major civil construction",
            "pure software implementation",
            "food supply",
            "legal services",
            "major design/build construction",
        ],
        "response_days_available": 12,
    },
}


def supported_profiles() -> list[dict[str, Any]]:
    return [deepcopy(SUPPORTED_PROFILE_PAYLOADS[profile_id]) for profile_id in SUPPORTED_PROFILE_IDS]


def get_supported_profile(profile_id: str | None) -> BusinessProfile:
    key = str(profile_id or "").strip().lower()
    payload = SUPPORTED_PROFILE_PAYLOADS.get(key) or SUPPORTED_PROFILE_PAYLOADS["building_mechanical"]
    return BusinessProfile.from_payload(deepcopy(payload))


def profile_from_payload(payload: dict[str, Any] | None) -> BusinessProfile:
    payload = payload or {}
    nested = payload.get("business_profile") if isinstance(payload.get("business_profile"), dict) else {}
    profile_id = str(
        payload.get("profile_id")
        or payload.get("supported_profile")
        or nested.get("profile_id")
        or nested.get("supported_profile")
        or ""
    ).strip().lower()
    if profile_id in SUPPORTED_PROFILE_PAYLOADS:
        base = deepcopy(SUPPORTED_PROFILE_PAYLOADS[profile_id])
        overrides = payload.get("business_profile")
        if isinstance(overrides, dict):
            base.update(overrides)
            base["profile_id"] = profile_id
        else:
            for key, value in payload.items():
                if key not in {"business_profile", "supported_profile"}:
                    base[key] = value
        return BusinessProfile.from_payload(base)
    return BusinessProfile.from_payload(payload.get("business_profile") if isinstance(payload.get("business_profile"), dict) else payload)
