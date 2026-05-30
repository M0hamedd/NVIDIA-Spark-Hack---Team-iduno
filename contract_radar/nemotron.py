from __future__ import annotations

import json
import os
import re
import socket
import time
from dataclasses import replace
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from contract_radar.models import BusinessProfile, EvaluatedOpportunity, RequirementExtraction


DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"
TOP_CANDIDATE_LIMIT = 3
NIM_PREFLIGHT_TIMEOUT_SECONDS = 0.2
NIM_PREFLIGHT_CACHE_SECONDS = 30.0
_NIM_PREFLIGHT_CACHE: dict[str, dict[str, Any]] = {}

REQUIREMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "services": {"type": "array", "items": {"type": "string"}},
        "certifications": {"type": "array", "items": {"type": "string"}},
        "documents": {"type": "array", "items": {"type": "string"}},
        "facility_signals": {"type": "array", "items": {"type": "string"}},
        "risk_flags": {"type": "array", "items": {"type": "string"}},
        "capacity_flags": {"type": "array", "items": {"type": "string"}},
        "procurement_type": {"type": "string"},
        "deadline_risk": {"type": "string"},
        "next_action": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": [
        "services",
        "certifications",
        "documents",
        "facility_signals",
        "risk_flags",
        "capacity_flags",
        "procurement_type",
        "deadline_risk",
        "next_action",
        "summary",
    ],
    "additionalProperties": False,
}

SERVICE_TERMS = {
    "road repairs": ("road repair", "road repairs", "road rehabilitation", "road corridor"),
    "sidewalk repairs": ("sidewalk repair", "sidewalk repairs", "sidewalk construction"),
    "bridge rehabilitation": ("bridge rehabilitation", "bridge deck", "bridge repairs"),
    "watermain construction": ("watermain", "water main"),
    "sewer rehabilitation": ("sewer rehabilitation", "sewer repair", "sewer"),
    "curb repair": ("curb repair", "curb repairs", "curbs"),
    "asphalt paving": ("asphalt", "paving"),
    "traffic staging": ("traffic staging", "traffic control"),
    "park improvements": ("park improvement", "park improvements", "park renewal"),
    "playground installation": ("playground", "playground installation"),
    "splash pad repairs": ("splash pad", "splashpad"),
    "landscaping": ("landscaping", "landscape"),
    "tree and arborist services": ("arborist", "tree service", "tree services"),
    "trail repairs": ("trail repair", "trail repairs", "trail"),
    "professional consulting engineering services": ("professional consulting engineering", "engineering services"),
    "preliminary design": ("preliminary design",),
    "detailed design": ("detailed design", "detail design"),
    "tender preparation": ("tender preparation",),
    "construction contract administration": ("contract administration",),
    "HVAC maintenance": ("hvac", "heating", "ventilation", "air conditioning"),
    "building automation systems/BAS controls": ("building automation", "bas", "controls", "automation"),
    "boiler service": ("boiler", "boilers"),
    "chiller service": ("chiller", "chillers"),
    "emergency repairs": ("emergency", "urgent", "after-hours", "after hours"),
    "preventative maintenance": ("preventative", "preventive", "maintenance"),
    "energy retrofit support": ("energy retrofit", "retrofit", "energy efficiency"),
    "mechanical repairs": ("mechanical repair", "mechanical repairs"),
}
CERTIFICATION_TERMS = {
    "technician certification": ("certified", "certification", "licensed technician", "technician"),
    "TSSA or gas fitter review": ("tssa", "gas fitter", "gasfitter", "fuel safety"),
    "refrigeration mechanic review": ("refrigeration", "refrigerant", "chiller"),
}
DOCUMENT_TERMS = {
    "insurance": ("insurance",),
    "WSIB": ("wsib",),
    "HST": ("hst",),
    "references": ("references", "reference"),
    "bonding": ("bond", "bonding", "bid bond"),
}
FACILITY_TERMS = {
    "municipal facility": ("municipal", "city-operated", "city operated", "public facility"),
    "library": ("library", "libraries"),
    "recreation centre": ("recreation", "arena", "community centre", "community center"),
    "office facility": ("office", "corporate real estate"),
    "multi-site work": ("multiple sites", "various locations", "all wards"),
}
RISK_TERMS = {
    "large construction scope": ("construction", "design-build", "design build", "general contractor"),
    "software-only scope": ("software", "platform", "data migration", "licensing"),
    "road or landscaping scope": ("road paving", "paving", "landscaping", "curb repair"),
    "food supply scope": ("food", "beverages", "serving materials"),
    "bonding may be required": ("bond", "bonding"),
}


def nemotron_status() -> dict[str, Any]:
    base_url = _base_url()
    model = os.environ.get("NIM_MODEL", DEFAULT_MODEL)
    availability = _nim_preflight()
    return {
        "mode": "local_nim_optional",
        "base_url": base_url,
        "model": model,
        "available": availability["available"],
        "nim_mode": "local_nim_available" if availability["available"] else "deterministic_fallback",
        "preflight": availability,
        "api_key_configured": bool(os.environ.get("NIM_API_KEY")),
        "fallback": "deterministic_fallback",
        "structured_extraction": True,
        "top_candidate_limit": TOP_CANDIDATE_LIMIT,
        "story": (
            "Nemotron is used after deterministic filtering to extract structured procurement "
            "requirements from shortlisted contracts. The bid-fitness engine keeps ownership "
            "of Pursue/Review/Monitor/Skip decisions. If local NIM is offline, the app falls "
            "back to deterministic extraction and summaries."
        ),
    }


def enrich_top_opportunities(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
) -> tuple[list[EvaluatedOpportunity], str]:
    enriched, mode = _enrich_top_opportunities(profile, opportunities, return_stats=False)
    return enriched, mode


def enrich_top_opportunities_with_stats(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
) -> tuple[list[EvaluatedOpportunity], str, dict[str, Any]]:
    return _enrich_top_opportunities(profile, opportunities, return_stats=True)


def _enrich_top_opportunities(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
    return_stats: bool,
) -> tuple[list[EvaluatedOpportunity], str] | tuple[list[EvaluatedOpportunity], str, dict[str, Any]]:
    stats = _empty_enrichment_stats(len(opportunities))
    if not opportunities:
        return _with_optional_stats([], "deterministic_fallback", stats, return_stats)

    top_count = min(TOP_CANDIDATE_LIMIT, len(opportunities))
    stats["shortlisted_for_model"] = top_count
    availability = _nim_preflight()
    stats["nim_preflight"] = availability
    if not availability["available"]:
        stats["model_calls_avoided_by_preflight"] = top_count
        return _with_optional_stats(
            _fallback_enrich(profile, opportunities),
            "deterministic_fallback",
            stats,
            return_stats,
        )

    enriched: list[EvaluatedOpportunity] = []
    mode = "local_nim"

    for index, opportunity in enumerate(opportunities):
        if index >= top_count:
            enriched.append(_with_fallback_requirements(profile, opportunity))
            continue
        try:
            stats["model_calls_attempted"] += 1
            extraction = _extract_with_nim(profile, opportunity)
            enriched.append(_with_extraction(profile, opportunity, extraction))
        except Exception:
            mode = "deterministic_fallback"
            _open_nim_circuit()
            stats["model_calls_failed"] += 1
            stats["model_calls_avoided_by_failure"] = top_count - stats["model_calls_attempted"]
            return _with_optional_stats(
                _fallback_enrich(profile, opportunities),
                mode,
                stats,
                return_stats,
            )

    return _with_optional_stats(enriched, mode, stats, return_stats)


def _extract_with_nim(profile: BusinessProfile, opportunity: EvaluatedOpportunity) -> RequirementExtraction:
    prompt = _structured_prompt(profile, opportunity)
    try:
        content = _chat_completion(prompt, with_schema=True)
    except RuntimeError:
        content = _chat_completion(prompt, with_schema=False)
    payload = _extract_json_object(content)
    return _validate_extraction(payload, source="local_nim")


def _chat_completion(prompt: str, with_schema: bool) -> str:
    payload: dict[str, Any] = {
        "model": os.environ.get("NIM_MODEL", DEFAULT_MODEL),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You extract procurement requirements for a local bid intelligence system. "
                    "Use only the supplied evidence. Return JSON only. Do not decide whether "
                    "the business should bid."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 650,
    }
    if with_schema:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "procurement_requirement_extraction",
                "schema": REQUIREMENT_SCHEMA,
                "strict": True,
            },
        }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("NIM_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    endpoint = f"{_base_url()}/chat/completions"
    timeout = float(os.environ.get("NIM_TIMEOUT_SECONDS", "3.0"))
    req = request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        if with_schema and exc.code in {400, 404, 422}:
            raise RuntimeError("NIM endpoint rejected response_format") from exc
        raise RuntimeError("local NIM request failed") from exc
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError("local NIM unavailable") from exc

    data = json.loads(response_body)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "").strip()


def _fallback_enrich(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
) -> list[EvaluatedOpportunity]:
    return [_with_fallback_requirements(profile, item) for item in opportunities]


def _with_extraction(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    extraction: RequirementExtraction,
) -> EvaluatedOpportunity:
    return replace(
        opportunity,
        requirements=extraction,
        nemotron_summary=_summary_from_requirements(profile, opportunity, extraction),
    )


def _with_fallback_requirements(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
) -> EvaluatedOpportunity:
    extraction = _fallback_extraction(profile, opportunity)
    return _with_extraction(profile, opportunity, extraction)


def _fallback_extraction(profile: BusinessProfile, opportunity: EvaluatedOpportunity) -> RequirementExtraction:
    solicitation = opportunity.solicitation
    text = _solicitation_text(opportunity)
    services = _term_matches(text, SERVICE_TERMS) or list(opportunity.matched_terms[:5])
    certifications = _term_matches(text, CERTIFICATION_TERMS)
    documents = _term_matches(text, DOCUMENT_TERMS)
    facility_signals = _term_matches(text, FACILITY_TERMS)
    risk_flags = _term_matches(text, RISK_TERMS)
    capacity_flags = _capacity_flags(profile, opportunity, risk_flags)
    deadline_risk = _deadline_risk(opportunity.days_until_deadline)
    next_action = _next_action(opportunity, risk_flags, capacity_flags)
    procurement_type = solicitation.solicitation_type or "Solicitation"
    summary = _compact_summary(services, risk_flags, capacity_flags, deadline_risk)
    return RequirementExtraction(
        source="deterministic_fallback",
        services=services,
        certifications=certifications,
        documents=documents,
        facility_signals=facility_signals,
        risk_flags=risk_flags,
        capacity_flags=capacity_flags,
        procurement_type=procurement_type,
        deadline_risk=deadline_risk,
        next_action=next_action,
        summary=summary,
    )


def _structured_prompt(profile: BusinessProfile, opportunity: EvaluatedOpportunity) -> str:
    solicitation = opportunity.solicitation
    return json.dumps(
        {
            "task": (
                "Extract structured procurement requirements. Return one JSON object matching the schema. "
                "Do not invent requirements. Empty arrays are allowed."
            ),
            "business_context": {
                "name": profile.name,
                "business_type": profile.business_type,
                "team_size": profile.team_size,
                "max_contract_value": profile.max_contract_value,
                "max_sites_per_day": profile.max_sites_per_day,
                "skills": profile.skills,
                "ready_documents": profile.ready_documents,
                "known_missing_capabilities": profile.missing_capabilities,
            },
            "solicitation": {
                "document_number": solicitation.document_number,
                "type": solicitation.solicitation_type,
                "category": solicitation.category,
                "description": solicitation.description,
                "division": solicitation.division,
                "deadline": solicitation.submission_deadline.isoformat()
                if solicitation.submission_deadline
                else None,
                "buyer": solicitation.buyer_name,
            },
            "computed_evidence": {
                "current_decision_label": opportunity.label,
                "matched_terms": opportunity.matched_terms,
                "missing_requirements": opportunity.missing_requirements,
                "reasons": opportunity.reasons,
                "rejection_reasons": opportunity.rejection_reasons,
                "days_until_deadline": opportunity.days_until_deadline,
                "historical": opportunity.historical.to_dict(),
            },
            "schema_fields": {
                "services": "service requirements explicitly implied by the solicitation",
                "certifications": "certifications/licenses/technical credentials that may be required",
                "documents": "insurance, WSIB, bonds, references, forms, or portal documents",
                "facility_signals": "facility, location, or site-type clues",
                "risk_flags": "scope or eligibility risks",
                "capacity_flags": "team size, multi-site, deadline, or delivery capacity concerns",
                "procurement_type": "RFQ, RFP, RFSQ, Tender, or the listed solicitation type",
                "deadline_risk": "Manageable, Tight, Critical, or Unknown",
                "next_action": "short next action for the owner",
                "summary": "one concise evidence-only sentence",
            },
        }
    )


def _validate_extraction(payload: dict[str, Any], source: str) -> RequirementExtraction:
    return RequirementExtraction(
        source=source,
        services=_string_list(payload.get("services")),
        certifications=_string_list(payload.get("certifications")),
        documents=_string_list(payload.get("documents")),
        facility_signals=_string_list(payload.get("facility_signals")),
        risk_flags=_string_list(payload.get("risk_flags")),
        capacity_flags=_string_list(payload.get("capacity_flags")),
        procurement_type=_short_text(payload.get("procurement_type")),
        deadline_risk=_normal_deadline_risk(payload.get("deadline_risk")),
        next_action=_short_text(payload.get("next_action"), limit=160),
        summary=_short_text(payload.get("summary"), limit=240),
    )


def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if not text:
        raise ValueError("empty NIM response")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("NIM extraction was not a JSON object")
    return payload


def _summary_from_requirements(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    extraction: RequirementExtraction,
) -> str:
    services = _join_or_default(extraction.services or opportunity.matched_terms, "no explicit service terms")
    risks = _join_or_default(extraction.risk_flags + extraction.capacity_flags, "no major blocker identified")
    history = opportunity.historical
    if history.similar_count:
        award_signal = f"{history.similar_count} similar awards, median ${history.award_median:,.0f}"
    else:
        award_signal = "insufficient similar award history"
    next_action = extraction.next_action or _next_action(opportunity, extraction.risk_flags, extraction.capacity_flags)
    return (
        f"{opportunity.label}: {opportunity.solicitation.description or opportunity.solicitation.document_number}. "
        f"For {profile.name}, extracted services are {services}. "
        f"Risks: {risks}. Historical signal: {award_signal}. Next action: {next_action}."
    )


def _term_matches(text: str, term_map: dict[str, tuple[str, ...]]) -> list[str]:
    matches = []
    lowered = text.lower()
    for label, terms in term_map.items():
        if any(term in lowered for term in terms):
            matches.append(label)
    return matches


def _capacity_flags(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    risk_flags: list[str],
) -> list[str]:
    flags: list[str] = []
    if opportunity.days_until_deadline is None:
        flags.append("deadline not listed")
    elif opportunity.days_until_deadline < 5:
        flags.append("tight response window")
    if opportunity.historical.award_median > profile.max_contract_value:
        flags.append("historical award size above preferred range")
    if any("large construction" in flag for flag in risk_flags):
        flags.append("delivery capacity likely too large")
    if len(opportunity.missing_requirements) >= 2:
        flags.append("multiple missing requirements")
    return flags


def _deadline_risk(days_until_deadline: int | None) -> str:
    if days_until_deadline is None:
        return "Unknown"
    if days_until_deadline < 0:
        return "Critical"
    if days_until_deadline < 5:
        return "Critical"
    if days_until_deadline <= 10:
        return "Tight"
    return "Manageable"


def _next_action(
    opportunity: EvaluatedOpportunity,
    risk_flags: list[str],
    capacity_flags: list[str],
) -> str:
    if opportunity.label == "Skip":
        return "Do not spend owner time on this opportunity."
    if capacity_flags or risk_flags or opportunity.label == "Review":
        return "Review risks and capacity before preparing a response."
    if opportunity.label == "Pursue":
        return "Prepare owner review package and confirm documents."
    return "Monitor for addenda or a stronger fit signal."


def _compact_summary(
    services: list[str],
    risk_flags: list[str],
    capacity_flags: list[str],
    deadline_risk: str,
) -> str:
    service_text = _join_or_default(services, "no explicit service requirement")
    risk_text = _join_or_default(risk_flags + capacity_flags, "no major risk")
    return f"Services: {service_text}. Risks: {risk_text}. Deadline risk: {deadline_risk}."


def _solicitation_text(opportunity: EvaluatedOpportunity) -> str:
    solicitation = opportunity.solicitation
    return " ".join(
        [
            solicitation.solicitation_type,
            solicitation.category,
            solicitation.description,
            solicitation.division,
            " ".join(opportunity.reasons),
            " ".join(opportunity.rejection_reasons),
        ]
    )


def _string_list(value: Any, limit: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        text = _short_text(item, limit=90)
        if text:
            cleaned.append(text)
    return cleaned[:limit]


def _short_text(value: Any, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    return text[:limit].strip()


def _normal_deadline_risk(value: Any) -> str:
    text = _short_text(value, limit=40).lower()
    if "critical" in text:
        return "Critical"
    if "tight" in text:
        return "Tight"
    if "manage" in text or "enough" in text:
        return "Manageable"
    if "unknown" in text or "not" in text:
        return "Unknown"
    return _short_text(value, limit=40)


def _empty_enrichment_stats(opportunity_count: int) -> dict[str, Any]:
    return {
        "opportunity_count": opportunity_count,
        "shortlisted_for_model": 0,
        "model_calls_attempted": 0,
        "model_calls_failed": 0,
        "model_calls_avoided_by_preflight": 0,
        "model_calls_avoided_by_failure": 0,
        "nim_preflight": {"available": False, "reason": "not_checked"},
    }


def _with_optional_stats(
    enriched: list[EvaluatedOpportunity],
    mode: str,
    stats: dict[str, Any],
    return_stats: bool,
) -> tuple[list[EvaluatedOpportunity], str] | tuple[list[EvaluatedOpportunity], str, dict[str, Any]]:
    if return_stats:
        return enriched, mode, stats
    return enriched, mode


def _nim_preflight() -> dict[str, Any]:
    base_url = _base_url()
    now = time.monotonic()
    cache_key = base_url
    cached = _NIM_PREFLIGHT_CACHE.get(cache_key)
    cache_seconds = float(os.environ.get("NIM_PREFLIGHT_CACHE_SECONDS", str(NIM_PREFLIGHT_CACHE_SECONDS)))
    if cached and now - float(cached.get("checked_at", 0.0)) <= cache_seconds:
        return {
            key: value
            for key, value in cached.items()
            if key != "checked_at"
        }

    parsed = urlparse(base_url)
    host = parsed.hostname
    if not host:
        result = {"available": False, "reason": "invalid_base_url", "base_url": base_url}
        _cache_nim_preflight(cache_key, result)
        return result
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    timeout = float(os.environ.get("NIM_PREFLIGHT_TIMEOUT_SECONDS", str(NIM_PREFLIGHT_TIMEOUT_SECONDS)))
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        result = {
            "available": False,
            "reason": "connection_failed",
            "base_url": base_url,
            "host": host,
            "port": port,
            "detail": str(exc)[:120],
        }
        _cache_nim_preflight(cache_key, result)
        return result

    result = {
        "available": True,
        "reason": "tcp_ready",
        "base_url": base_url,
        "host": host,
        "port": port,
    }
    _cache_nim_preflight(cache_key, result)
    return result


def _cache_nim_preflight(cache_key: str, result: dict[str, Any]) -> None:
    payload = dict(result)
    payload["checked_at"] = time.monotonic()
    _NIM_PREFLIGHT_CACHE[cache_key] = payload


def _open_nim_circuit() -> None:
    result = {
        "available": False,
        "reason": "request_failed_circuit_open",
        "base_url": _base_url(),
    }
    _cache_nim_preflight(_base_url(), result)


def reset_nim_preflight_cache() -> None:
    _NIM_PREFLIGHT_CACHE.clear()


def _base_url() -> str:
    return os.environ.get("NIM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _join_or_default(values: list[str], default: str) -> str:
    cleaned = [value for value in values if value]
    return ", ".join(cleaned[:5]) if cleaned else default
