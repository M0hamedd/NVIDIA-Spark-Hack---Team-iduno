from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sparkterritory.config import SCORE_WEIGHTS
from sparkterritory.data import DataSignals
from sparkterritory.geo import district_from_neighbourhood, operational_score
from sparkterritory.utils import log_signal, minmax, normalize_name, safe_divide


@dataclass
class BusinessProfile:
    business_type: str = "window_washing"
    crew_size: int = 2
    base_neighbourhood: str = "Scarborough Village"
    max_travel_minutes: int = 30
    customer_focus: str = "residential"
    priority_mode: str = "balanced"

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "BusinessProfile":
        return cls(
            business_type=str(payload.get("business_type") or "window_washing"),
            crew_size=max(1, int(payload.get("crew_size") or 2)),
            base_neighbourhood=str(payload.get("base_neighbourhood") or "Scarborough Village"),
            max_travel_minutes=max(10, int(payload.get("max_travel_minutes") or 30)),
            customer_focus=str(payload.get("customer_focus") or "residential"),
            priority_mode=str(payload.get("priority_mode") or "balanced"),
        )


def score_neighbourhoods(profile: BusinessProfile, signals: DataSignals) -> list[dict[str, Any]]:
    base_district = _base_district(profile, signals)
    weights = weights_for_profile(profile)
    raw_rows: list[dict[str, Any]] = []
    for name, metrics in signals.neighbourhoods.items():
        district = str(metrics.get("district") or district_from_neighbourhood(name, metrics.get("number")))
        current = signals.current_by_district.get(district, {})
        growth = signals.growth_by_district.get(district, {})
        future = signals.future_by_district.get(district, {})
        highrise_share = float(metrics.get("highrise_share") or safe_divide(float(metrics.get("highrise_apartments") or 0), float(metrics.get("dwellings") or 0)))
        customer_raw = (
            log_signal(float(metrics.get("avg_income") or 0)) * 0.42
            + log_signal(float(metrics.get("density") or 0)) * 0.26
            + log_signal(float(metrics.get("dwellings") or 0)) * 0.17
            + highrise_share * 6.0
        )
        raw_rows.append(
            {
                "name": name,
                "district": district,
                "metrics": metrics,
                "current_raw": float(current.get("weighted_value") or 0),
                "future_raw": _future_value(future),
                "growth_raw": float(growth.get("weighted_value") or 0),
                "customer_raw": customer_raw,
                "current": current,
                "future": future,
                "growth": growth,
                "operational_feasibility_score": operational_score(
                    base_district, district, profile.max_travel_minutes
                ),
            }
        )

    current_values = [row["current_raw"] for row in raw_rows]
    future_values = [row["future_raw"] for row in raw_rows]
    growth_values = [row["growth_raw"] for row in raw_rows]
    customer_values = [row["customer_raw"] for row in raw_rows]

    scored: list[dict[str, Any]] = []
    for row in raw_rows:
        current_score = round(minmax(row["current_raw"], current_values))
        future_score = round(minmax(row["future_raw"], future_values))
        customer_score = round(minmax(row["customer_raw"], customer_values))
        growth_score = round(minmax(row["growth_raw"], growth_values))
        operational = round(row["operational_feasibility_score"])
        prospect_score = round((customer_score * 0.55) + (future_score * 0.25) + (current_score * 0.20))
        overall = round(
            current_score * weights["current_demand_score"]
            + future_score * weights["future_growth_score"]
            + customer_score * weights["customer_fit_score"]
            + growth_score * weights["growth_momentum_score"]
            + operational * weights["operational_feasibility_score"]
        )
        evidence = build_evidence(row, current_score, future_score, customer_score, growth_score, operational)
        positives, negatives = factor_summary(row, current_score, future_score, customer_score, growth_score, operational)
        prospect_count = estimate_prospects(row, profile)
        confidence, confidence_reason = confidence_summary(current_score, future_score, customer_score, growth_score)
        scored.append(
            {
                "name": row["name"],
                "district": row["district"],
                "id": normalize_name(row["name"]).replace(" ", "-").replace("/", "-"),
                "overall_score": overall,
                "current_demand_score": current_score,
                "future_growth_score": future_score,
                "customer_fit_score": customer_score,
                "growth_momentum_score": growth_score,
                "operational_feasibility_score": operational,
                "prospect_score": prospect_score,
                "component_scores": {
                    "demand": current_score,
                    "growth": max(future_score, growth_score),
                    "prospects": prospect_score,
                    "customer_quality": customer_score,
                    "crew_feasibility": operational,
                },
                "confidence": confidence,
                "confidence_reason": confidence_reason,
                "top_positive_factors": positives,
                "top_negative_factors": negatives,
                "prospect_count": prospect_count,
                "sales_targets_nearby": sales_target_summary(row, prospect_count, profile),
                "evidence": evidence,
                "recommended_action": recommended_action(row["name"], row["district"], profile),
                "map": map_position(row["name"], row["district"]),
                "raw_signals": {
                    "active_permit_records_in_district": round(float(row["current"].get("records") or 0)),
                    "cleared_permit_records_in_district": round(float(row["growth"].get("records") or 0)),
                    "proposed_residential_units_in_district": round(float(row["future"].get("residential_units") or 0)),
                    "profile_avg_income": round(float(row["metrics"].get("avg_income") or 0)),
                    "profile_density_per_sq_km": round(float(row["metrics"].get("density") or 0)),
                    "profile_highrise_apartments": round(float(row["metrics"].get("highrise_apartments") or 0)),
                },
            }
        )
    return sorted(scored, key=lambda item: item["overall_score"], reverse=True)


def weights_for_profile(profile: BusinessProfile) -> dict[str, float]:
    weights = dict(SCORE_WEIGHTS)
    business = profile.business_type
    if business in {"hvac", "mechanical_services"}:
        weights.update(
            {
                "current_demand_score": 0.32,
                "future_growth_score": 0.18,
                "customer_fit_score": 0.24,
                "growth_momentum_score": 0.18,
                "operational_feasibility_score": 0.08,
            }
        )
    elif business in {"landscaping", "grounds"}:
        weights.update(
            {
                "current_demand_score": 0.22,
                "future_growth_score": 0.14,
                "customer_fit_score": 0.30,
                "growth_momentum_score": 0.12,
                "operational_feasibility_score": 0.22,
            }
        )
    elif business in {"pest_control"}:
        weights.update(
            {
                "current_demand_score": 0.28,
                "future_growth_score": 0.16,
                "customer_fit_score": 0.25,
                "growth_momentum_score": 0.16,
                "operational_feasibility_score": 0.15,
            }
        )
    elif business in {"cleaning_maintenance", "commercial_cleaning"}:
        weights.update(
            {
                "current_demand_score": 0.30,
                "future_growth_score": 0.20,
                "customer_fit_score": 0.24,
                "growth_momentum_score": 0.12,
                "operational_feasibility_score": 0.14,
            }
        )

    if profile.priority_mode == "growth":
        weights["future_growth_score"] += 0.08
        weights["growth_momentum_score"] += 0.04
        weights["operational_feasibility_score"] -= 0.04
        weights["current_demand_score"] -= 0.04
        weights["customer_fit_score"] -= 0.04
    elif profile.priority_mode == "low_friction":
        weights["operational_feasibility_score"] += 0.10
        weights["future_growth_score"] -= 0.04
        weights["growth_momentum_score"] -= 0.03
        weights["current_demand_score"] -= 0.03
    elif profile.priority_mode == "high_value":
        weights["customer_fit_score"] += 0.08
        weights["future_growth_score"] += 0.03
        weights["operational_feasibility_score"] -= 0.04
        weights["growth_momentum_score"] -= 0.03
        weights["current_demand_score"] -= 0.04

    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def split_recommendations(scored: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target_now = scored[:5]
    future_candidates = sorted(
        scored,
        key=lambda item: (item["future_growth_score"], item["customer_fit_score"], item["overall_score"]),
        reverse=True,
    )
    target_names = {item["name"] for item in target_now}
    expand_next = [item for item in future_candidates if item["name"] not in target_names][:3]
    return target_now, expand_next


def downtown_tradeoff(scored: list[dict[str, Any]]) -> str:
    downtown = [item for item in scored if item["district"] == "Downtown"]
    if not downtown:
        return "Downtown was not scored because the current dataset join produced no downtown neighbourhood records."
    best = max(downtown, key=lambda item: item["overall_score"])
    rank = scored.index(best) + 1
    if rank <= 5:
        return (
            f"Downtown is still competitive: {best['name']} ranks #{rank}. "
            "For a small crew, compare its density upside against parking, travel, and scheduling friction."
        )
    return (
        f"Downtown density is real, but the best downtown fit here is {best['name']} at rank #{rank}. "
        "The current scenario rewards nearer, easier-to-cluster districts for a 2-person crew."
    )


def build_evidence(
    row: dict[str, Any],
    current_score: int,
    future_score: int,
    customer_score: int,
    growth_score: int,
    operational_score_value: int,
) -> list[str]:
    evidence = [
        f"{row['district']} active permit signal scores {current_score}/100 for current window-cleaning demand.",
        f"{row['district']} development pipeline signal scores {future_score}/100 for future expansion.",
        f"Neighbourhood customer-fit profile scores {customer_score}/100 using income, density, dwellings, and high-rise indicators.",
    ]
    if growth_score >= 60:
        evidence.append(f"Cleared permit momentum scores {growth_score}/100, suggesting recent construction and renovation activity.")
    if operational_score_value >= 75:
        evidence.append(f"Operational feasibility scores {operational_score_value}/100 from the selected base and travel limit.")
    elif operational_score_value < 50:
        evidence.append(f"Operational feasibility is only {operational_score_value}/100, so this is better as an expansion target than a first-week route.")
    return evidence


def factor_summary(
    row: dict[str, Any],
    current_score: int,
    future_score: int,
    customer_score: int,
    growth_score: int,
    operational_score_value: int,
) -> tuple[list[str], list[str]]:
    positives: list[str] = []
    negatives: list[str] = []
    if current_score >= 70:
        positives.append("Strong near-term permit activity points to immediate work.")
    if future_score >= 70:
        positives.append("Development pipeline suggests future recurring building demand.")
    if customer_score >= 70:
        positives.append("Dense housing and income profile support higher-value routes.")
    if growth_score >= 65:
        positives.append("Recent cleared permits show renovation momentum.")
    if operational_score_value >= 75:
        positives.append("Crew can cluster jobs from the selected base with limited travel drag.")
    if not positives:
        positives.append("Balanced signal mix keeps this area in the target set.")

    if operational_score_value < 55:
        negatives.append("Crew feasibility is weaker from the selected base.")
    if current_score < 45:
        negatives.append("Immediate permit demand is below the top Toronto zones.")
    if future_score < 45:
        negatives.append("Future development signal is less pronounced.")
    if customer_score < 45:
        negatives.append("Customer-density fit is thinner than the leading zones.")
    if not negatives:
        negatives.append("Main risk is execution capacity: confirm access, scheduling, and sales coverage.")
    return positives[:3], negatives[:3]


def estimate_prospects(row: dict[str, Any], profile: BusinessProfile) -> int:
    metrics = row["metrics"]
    current = row["current"]
    future = row["future"]
    highrise = float(metrics.get("highrise_apartments") or 0)
    dwellings = float(metrics.get("dwellings") or 0)
    active_records = float(current.get("records") or 0)
    applications = float(future.get("applications") or 0)
    base = highrise / 85.0 + dwellings / 1450.0 + active_records / 42.0 + applications / 3.5
    if profile.customer_focus == "commercial":
        base *= 1.18
    if profile.business_type in {"cleaning_maintenance", "commercial_cleaning"}:
        base *= 1.12
    return max(8, round(base))


def sales_target_summary(row: dict[str, Any], prospect_count: int, profile: BusinessProfile) -> dict[str, Any]:
    business = profile.business_type
    if business in {"hvac", "mechanical_services"}:
        examples = ["property managers", "older multifamily buildings", "renovation sites"]
    elif business in {"pest_control"}:
        examples = ["apartment managers", "food-service corridors", "mixed-use buildings"]
    elif business in {"landscaping", "grounds"}:
        examples = ["townhome clusters", "condo grounds boards", "high-income residential streets"]
    elif business in {"cleaning_maintenance", "commercial_cleaning"}:
        examples = ["offices", "retail corridors", "apartment common-area managers"]
    else:
        examples = ["condo boards", "apartment managers", "commercial glass storefronts"]
    return {
        "estimated_targets": prospect_count,
        "examples": examples,
        "source_hint": "permits, neighbourhood profiles, apartments, commercial corridors, and development signals",
    }


def confidence_summary(current_score: int, future_score: int, customer_score: int, growth_score: int) -> tuple[str, str]:
    strong = sum(score >= 65 for score in (current_score, future_score, customer_score, growth_score))
    weak = sum(score < 40 for score in (current_score, future_score, customer_score, growth_score))
    if strong >= 3 and weak == 0:
        return "High", "Multiple independent signals agree: demand, growth, and customer fit are all strong."
    if strong >= 2 and weak <= 1:
        return "Medium-high", "Two or more signals are strong, with one area to verify before committing crews."
    if weak >= 2:
        return "Medium", "Useful opportunity, but the recommendation depends on fewer strong signals."
    return "Medium", "Signals are balanced enough for prospecting, but should be validated with local sales calls."


MAP_POSITIONS = {
    "Scarborough Village": {"x": 74, "y": 58, "w": 16, "h": 15},
    "Woburn": {"x": 70, "y": 34, "w": 18, "h": 16},
    "Willowdale East": {"x": 48, "y": 22, "w": 16, "h": 16},
    "Mimico (includes Humber Bay Shores)": {"x": 18, "y": 70, "w": 18, "h": 14},
    "Waterfront Communities-The Island": {"x": 45, "y": 72, "w": 18, "h": 12},
    "The Beaches": {"x": 63, "y": 67, "w": 16, "h": 12},
    "High Park-Swansea": {"x": 28, "y": 62, "w": 17, "h": 14},
    "Yonge-Eglinton": {"x": 46, "y": 45, "w": 15, "h": 14},
}

DISTRICT_POSITIONS = {
    "Scarborough": {"x": 73, "y": 48, "w": 17, "h": 14},
    "North York": {"x": 48, "y": 26, "w": 16, "h": 14},
    "Central Toronto": {"x": 47, "y": 44, "w": 15, "h": 13},
    "Downtown": {"x": 46, "y": 70, "w": 16, "h": 11},
    "East York": {"x": 62, "y": 63, "w": 15, "h": 12},
    "West Toronto": {"x": 30, "y": 62, "w": 16, "h": 13},
    "Etobicoke": {"x": 18, "y": 68, "w": 17, "h": 13},
}


def map_position(name: str, district: str) -> dict[str, float | str]:
    position = dict(MAP_POSITIONS.get(name) or DISTRICT_POSITIONS.get(district) or {"x": 50, "y": 50, "w": 14, "h": 12})
    position["type"] = "demo_geometry"
    return position


def recommended_action(name: str, district: str, profile: BusinessProfile) -> str:
    if profile.business_type in {"hvac", "mechanical_services"}:
        return f"Use {name} for a maintenance outreach sprint to older multifamily and renovation-heavy properties."
    if profile.business_type in {"pest_control"}:
        return f"Prioritize apartment managers and food-service corridors in {name} for recurring pest-control contracts."
    if profile.business_type in {"landscaping", "grounds"}:
        return f"Cluster grounds and seasonal exterior-care routes in {name}, starting with dense residential pockets."
    if profile.business_type in {"cleaning_maintenance", "commercial_cleaning"}:
        return f"Build a B2B list in {name} for offices, retail strips, and apartment common-area contracts."
    if profile.customer_focus == "commercial":
        return f"Use {name} as a B2B prospecting zone for storefronts, offices, property managers, and post-construction glass cleanup."
    if district in {"Downtown", "North York", "Etobicoke"}:
        return f"Target condo boards, apartment managers, and new-build handoff cleaning in {name}."
    return f"Run a clustered residential exterior-window campaign in {name}, prioritizing renovation-heavy streets and multi-unit buildings."


def _future_value(future: dict[str, Any]) -> float:
    if future.get("weighted_value"):
        return float(future["weighted_value"])
    return (
        log_signal(float(future.get("applications") or 0)) * 0.8
        + log_signal(float(future.get("residential_units") or 0)) * 1.4
        + log_signal(float(future.get("gross_floor_area") or 0) / 1000.0)
    )


def _base_district(profile: BusinessProfile, signals: DataSignals) -> str:
    wanted = normalize_name(profile.base_neighbourhood)
    for name, metrics in signals.neighbourhoods.items():
        if normalize_name(name) == wanted:
            return str(metrics.get("district") or district_from_neighbourhood(name, metrics.get("number")))
    return district_from_neighbourhood(profile.base_neighbourhood)
