from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from contract_radar.models import parse_date


DEFAULT_START_DATE = date(2026, 5, 30)
ACTION_LABELS = {"Pursue"}
WATCH_LABELS = {"Review", "Monitor"}


def simulate_month(scan_result: dict[str, Any], days: int = 30) -> list[dict[str, Any]]:
    """Create a deterministic monitoring timeline from a scan response."""
    window_days = max(1, int(days or 30))
    next_day_mode = window_days == 1
    start = parse_date(scan_result.get("as_of")) or DEFAULT_START_DATE
    if next_day_mode:
        start = start + timedelta(days=1)
    opportunities = _ordered_opportunities(scan_result)
    metrics = scan_result.get("metrics") or {}
    profile = scan_result.get("business_profile") or {}

    timeline: list[dict[str, Any]] = [
        _event(
            start,
            0,
            "scan_day",
            "Daily monitor completed" if next_day_mode else "Live scan completed",
            _scan_message(metrics, opportunities, next_day_mode),
            priority="system",
        )
    ]

    if not opportunities:
        timeline.append(
            _event(
                start,
                min(1, window_days - 1),
                "no_matches",
                "No owner action needed",
                _no_match_message(profile, next_day_mode),
                priority="low",
            )
        )
        return _sort_events(timeline)

    for index, opportunity in enumerate(opportunities):
        label = _value(opportunity, "label", "Skip")
        if label in ACTION_LABELS:
            alert_day = _clamp_day(0 if next_day_mode else index + 1, window_days)
            timeline.append(_new_alert_event(start, alert_day, opportunity, next_day_mode))
            if not next_day_mode:
                approval_day = _clamp_day(alert_day + 1, window_days)
                timeline.append(_approval_ready_event(start, approval_day, opportunity))
        elif label in WATCH_LABELS:
            watch_day = _clamp_day(0 if next_day_mode else index + 1, window_days)
            timeline.append(_watchlist_event(start, watch_day, opportunity))

        deadline_day = _deadline_day(opportunity, window_days)
        if deadline_day is not None:
            timeline.append(_deadline_event(start, deadline_day, opportunity))

    return _sort_events(timeline)


def _ordered_opportunities(scan_result: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    ordered: list[dict[str, Any]] = []
    for bucket in ("top_opportunities", "watchlist", "all_evaluated"):
        for item in scan_result.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            if _value(item, "label", "Skip") == "Skip":
                continue
            opportunity_id = _opportunity_id(item)
            if opportunity_id in seen:
                continue
            seen.add(opportunity_id)
            ordered.append(item)
    return ordered


def _new_alert_event(
    start: date,
    day: int,
    opportunity: dict[str, Any],
    next_day_mode: bool = False,
) -> dict[str, Any]:
    title = (
        f"{_value(opportunity, 'label')} alert surfaced"
        if next_day_mode
        else f"{_value(opportunity, 'label')} opportunity found"
    )
    message = (
        f"Next-day monitor surfaced {_title(opportunity)} because it matches {_matched_phrase(opportunity)}."
        if next_day_mode
        else f"{_title(opportunity)} matches {_matched_phrase(opportunity)}."
    )
    return _event(
        start,
        day,
        "new_alert",
        title,
        message,
        opportunity,
        priority="high",
    )


def _watchlist_event(start: date, day: int, opportunity: dict[str, Any]) -> dict[str, Any]:
    label = _value(opportunity, "label", "Monitor")
    action = "needs human review" if label == "Review" else "should be monitored"
    return _event(
        start,
        day,
        "watchlist_update",
        f"{label}: {_title(opportunity)}",
        f"This opportunity {action}; current evidence is {_matched_phrase(opportunity)}.",
        opportunity,
        priority="medium",
    )


def _deadline_event(start: date, day: int, opportunity: dict[str, Any]) -> dict[str, Any]:
    days_left = _value(opportunity, "days_until_deadline")
    return _event(
        start,
        day,
        "deadline_approaching",
        f"Deadline approaching: {_title(opportunity)}",
        f"Submission deadline is approaching with {days_left} day(s) left in the monitoring window.",
        opportunity,
        priority="high",
    )


def _approval_ready_event(start: date, day: int, opportunity: dict[str, Any]) -> dict[str, Any]:
    missing = _value(opportunity, "missing_requirements", []) or []
    missing_text = "no missing requirements flagged" if not missing else f"missing: {', '.join(missing[:3])}"
    return _event(
        start,
        day,
        "approval_ready",
        f"Approval packet ready: {_title(opportunity)}",
        f"Owner approval can generate the bid packet; {missing_text}.",
        opportunity,
        priority="high",
    )


def _deadline_day(opportunity: dict[str, Any], window_days: int) -> int | None:
    days_left = _value(opportunity, "days_until_deadline")
    if days_left is None:
        return None
    try:
        days_left_int = int(days_left)
    except (TypeError, ValueError):
        return None
    if days_left_int < 0 or days_left_int >= window_days:
        return None
    return max(0, days_left_int - 3)


def _event(
    start: date,
    day: int,
    event_type: str,
    title: str,
    message: str,
    opportunity: dict[str, Any] | None = None,
    priority: str = "medium",
) -> dict[str, Any]:
    event = {
        "day": day,
        "date": (start + timedelta(days=day)).isoformat(),
        "type": event_type,
        "title": title,
        "message": message,
        "priority": priority,
    }
    if opportunity is not None:
        event["opportunity_id"] = _opportunity_id(opportunity)
        event["label"] = _value(opportunity, "label")
    return event


def _scan_message(metrics: dict[str, Any], opportunities: list[dict[str, Any]], next_day_mode: bool = False) -> str:
    loaded = metrics.get("solicitations_loaded", 0)
    awards = metrics.get("awards_loaded", 0)
    if next_day_mode:
        return (
            f"Next-day monitor checked {loaded} solicitations, compared {awards} historical awards, "
            f"and surfaced {len(opportunities)} candidate(s)."
        )
    return f"Scanned {loaded} solicitations, compared {awards} historical awards, and tracked {len(opportunities)} candidate(s)."


def _no_match_message(profile: dict[str, Any], next_day_mode: bool) -> str:
    business_type = str(profile.get("business_type") or "this profile").strip()
    if next_day_mode:
        return f"The next-day monitor found no realistic bids for {business_type}."
    return "No realistic bid opportunities were found in this monitoring window."


def _sort_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    order = {
        "scan_day": 0,
        "new_alert": 1,
        "watchlist_update": 2,
        "deadline_approaching": 3,
        "approval_ready": 4,
        "no_matches": 5,
    }
    return sorted(events, key=lambda event: (event["day"], order.get(event["type"], 99), event.get("opportunity_id", "")))


def _clamp_day(day: int, window_days: int) -> int:
    return max(0, min(day, window_days - 1))


def _title(opportunity: dict[str, Any]) -> str:
    solicitation = _value(opportunity, "solicitation", {}) or {}
    return str(
        _value(solicitation, "description")
        or _value(solicitation, "document_number")
        or "Untitled opportunity"
    )


def _opportunity_id(opportunity: dict[str, Any]) -> str:
    solicitation = _value(opportunity, "solicitation", {}) or {}
    return str(_value(solicitation, "document_number") or _title(opportunity))


def _matched_phrase(opportunity: dict[str, Any]) -> str:
    terms = _value(opportunity, "matched_terms", []) or []
    if not terms:
        return "the business profile"
    return ", ".join(str(term) for term in terms[:4])


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)
