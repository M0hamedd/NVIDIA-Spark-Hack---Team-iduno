from __future__ import annotations

from copy import deepcopy
from typing import Any

from contract_radar.models import BusinessProfile


DEFAULT_PROFILE_ID = "road_civil_infrastructure"

SUPPORTED_PROFILE_IDS = (
    DEFAULT_PROFILE_ID,
    "parks_landscape",
    "professional_engineering_design",
)

PROFILE_ALIASES = {
    "building_mechanical": DEFAULT_PROFILE_ID,
    "design_engineering": "professional_engineering_design",
}


SUPPORTED_PROFILE_PAYLOADS: dict[str, dict[str, Any]] = {
    "road_civil_infrastructure": {
        "profile_id": "road_civil_infrastructure",
        "label": "Road/Civil Infrastructure Contractor",
        "name": "Harbourfront Civil Works Ltd.",
        "business_type": "road, sidewalk, bridge, sewer, watermain, paving, and civil infrastructure contractor",
        "base_location": "Toronto, GTA",
        "team_size": 28,
        "max_contract_value": 1800000,
        "max_sites_per_day": 4,
        "active_pursuit_count": 2,
        "max_active_pursuits": 4,
        "service_area": "Toronto",
        "lane_basis": "2026 YTD Toronto solicitations: roads, sidewalks, bridges, watermains, sewers, paving, traffic staging, and civil infrastructure repairs.",
        "ytd_solicitation_hits": 45,
        "exclusive_best_fit_hits": 29,
        "top_divisions": [
            "Transportation Services",
            "Engineering & Construction Services",
            "Toronto Water",
        ],
        "good_fit_examples": [
            "road and sidewalk repair",
            "bridge rehabilitation",
            "watermain and sewer work",
            "curb, asphalt, and traffic-stage construction",
        ],
        "bad_fit_examples": [
            "pure software implementation",
            "parks-only landscaping",
            "professional design-only studies",
            "food or office supply",
        ],
        "skills": [
            "road repairs",
            "sidewalk repairs",
            "bridge rehabilitation",
            "watermain construction",
            "sewer rehabilitation",
            "curb repair",
            "asphalt paving",
            "traffic staging",
            "civil infrastructure construction",
            "municipal road corridor work",
        ],
        "ready_documents": [
            "insurance",
            "WSIB",
            "HST",
            "bonding capacity",
            "municipal references",
            "traffic control plan",
        ],
        "missing_capabilities": [
            "professional engineering design only",
            "architectural consulting",
            "parks-only landscaping",
            "kitchen equipment",
            "pure software implementation",
            "food supply",
        ],
        "response_days_available": 14,
    },
    "parks_landscape": {
        "profile_id": "parks_landscape",
        "label": "Parks/Landscape Contractor",
        "name": "Greenline Parks & Landscape Ltd.",
        "business_type": "parks, playground, landscaping, arborist, trail, and public realm contractor",
        "base_location": "Toronto, GTA",
        "team_size": 16,
        "max_contract_value": 650000,
        "max_sites_per_day": 6,
        "active_pursuit_count": 1,
        "max_active_pursuits": 3,
        "service_area": "Toronto",
        "lane_basis": "2026 YTD Toronto solicitations: park, playground, splash pad, landscaping, arborist, trail, sports field, and public realm work.",
        "ytd_solicitation_hits": 42,
        "exclusive_best_fit_hits": 29,
        "top_divisions": [
            "Parks, Forestry & Recreation",
            "Engineering & Construction Services",
            "Transportation Services",
        ],
        "good_fit_examples": [
            "park improvements",
            "playground and splash pad installation",
            "landscaping and planting",
            "trail and sports field maintenance",
        ],
        "bad_fit_examples": [
            "major road reconstruction",
            "watermain and sewer rehabilitation",
            "professional engineering design only",
            "pure software implementation",
        ],
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
    "professional_engineering_design": {
        "profile_id": "professional_engineering_design",
        "label": "Professional Engineering/Design Firm",
        "name": "CivicWorks Design Studio",
        "business_type": "professional consulting engineering, architecture, planning, and design services firm",
        "base_location": "Toronto, GTA",
        "team_size": 15,
        "max_contract_value": 900000,
        "max_sites_per_day": 3,
        "active_pursuit_count": 2,
        "max_active_pursuits": 4,
        "service_area": "Toronto",
        "lane_basis": "2026 YTD Toronto solicitations: professional consulting engineering, preliminary/detail design, tender preparation, contract administration, architecture, and planning work.",
        "ytd_solicitation_hits": 23,
        "exclusive_best_fit_hits": 14,
        "top_divisions": [
            "Engineering & Construction Services",
            "Parks, Forestry & Recreation",
            "Corporate Real Estate Management",
        ],
        "good_fit_examples": [
            "professional consulting engineering",
            "preliminary and detailed design",
            "tender preparation",
            "construction contract administration",
        ],
        "bad_fit_examples": [
            "construction-only tender delivery",
            "road paving as contractor",
            "supply and delivery only",
            "food or facility operations supply",
        ],
        "skills": [
            "professional consulting engineering services",
            "preliminary design",
            "detailed design",
            "tender preparation",
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
}


def supported_profiles() -> list[dict[str, Any]]:
    return [deepcopy(SUPPORTED_PROFILE_PAYLOADS[profile_id]) for profile_id in SUPPORTED_PROFILE_IDS]


def _canonical_profile_id(profile_id: str | None) -> str:
    key = str(profile_id or "").strip().lower()
    return PROFILE_ALIASES.get(key, key)


def get_supported_profile(profile_id: str | None) -> BusinessProfile:
    key = _canonical_profile_id(profile_id)
    payload = SUPPORTED_PROFILE_PAYLOADS.get(key) or SUPPORTED_PROFILE_PAYLOADS[DEFAULT_PROFILE_ID]
    return BusinessProfile.from_payload(deepcopy(payload))


def profile_from_payload(payload: dict[str, Any] | None) -> BusinessProfile:
    payload = payload or {}
    nested = payload.get("business_profile") if isinstance(payload.get("business_profile"), dict) else {}
    profile_id = _canonical_profile_id(
        str(
            payload.get("profile_id")
            or payload.get("supported_profile")
            or nested.get("profile_id")
            or nested.get("supported_profile")
            or ""
        )
    )
    if profile_id in SUPPORTED_PROFILE_PAYLOADS:
        base = deepcopy(SUPPORTED_PROFILE_PAYLOADS[profile_id])
        overrides = payload.get("business_profile")
        if isinstance(overrides, dict):
            base.update(overrides)
            base["profile_id"] = profile_id
        else:
            for key, value in payload.items():
                if key not in {"business_profile", "supported_profile", "profile_id"}:
                    base[key] = value
            base["profile_id"] = profile_id
        return BusinessProfile.from_payload(base)
    return BusinessProfile.from_payload(payload.get("business_profile") if isinstance(payload.get("business_profile"), dict) else payload)
