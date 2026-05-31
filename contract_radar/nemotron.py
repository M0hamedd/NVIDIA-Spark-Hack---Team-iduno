from __future__ import annotations

import json
import os
import re
import time
from dataclasses import replace
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from contract_radar.models import BusinessProfile, EvaluatedOpportunity, OpportunityBrief, RequirementExtraction


DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"
TOP_CANDIDATE_LIMIT = int(os.environ.get("CONTRACT_RADAR_NIM_SHORTLIST_LIMIT", "24") or "24")
NIM_PREFLIGHT_TIMEOUT_SECONDS = 0.2
NIM_PREFLIGHT_CACHE_SECONDS = 30.0
_NIM_PREFLIGHT_CACHE: dict[str, dict[str, Any]] = {}


class SchemaRejectedError(RuntimeError):
    pass


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
        "delivery_complexity": {"type": "string"},
        "scope_size": {"type": "string"},
        "disqualifying_requirements": {"type": "array", "items": {"type": "string"}},
        "next_action": {"type": "string"},
        "summary": {"type": "string"},
        "owner_brief": {
            "type": "object",
            "properties": {
                "owner_summary": {"type": "string"},
                "fit_reason": {"type": "string"},
                "blockers": {"type": "array", "items": {"type": "string"}},
                "required_documents": {"type": "array", "items": {"type": "string"}},
                "missing_items": {"type": "array", "items": {"type": "string"}},
                "clarification_questions": {"type": "array", "items": {"type": "string"}},
                "next_steps": {"type": "array", "items": {"type": "string"}},
                "buyer_email_draft": {"type": "string"},
            },
            "required": [
                "owner_summary",
                "fit_reason",
                "blockers",
                "required_documents",
                "missing_items",
                "clarification_questions",
                "next_steps",
                "buyer_email_draft",
            ],
            "additionalProperties": False,
        },
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
        "owner_brief",
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
            "requirements and owner-ready bid briefs from shortlisted contracts. The bid-fitness "
            "engine keeps ownership of Pursue/Review/Monitor/Skip decisions, but validated "
            "Nemotron blockers can downgrade a candidate for owner review. If local NIM is "
            "offline, the app can still rank contracts, but owner-ready packet drafting is blocked."
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
        fallback = _fallback_enrich(profile, opportunities)
        stats["briefs_generated"] = sum(
            1 for item in fallback if item.opportunity_brief.owner_summary
        )
        return _with_optional_stats(
            fallback,
            "deterministic_fallback",
            stats,
            return_stats,
        )

    enriched: list[EvaluatedOpportunity] = []
    mode = "local_nim"

    for index, opportunity in enumerate(opportunities):
        if index >= top_count:
            fallback_item = _with_fallback_requirements(profile, opportunity)
            stats["briefs_generated"] += int(bool(fallback_item.opportunity_brief.owner_summary))
            enriched.append(fallback_item)
            continue
        try:
            stats["model_calls_attempted"] += 1
            extraction, brief = _extract_with_nim(profile, opportunity)
            enriched_item = _with_extraction(profile, opportunity, extraction, brief)
            stats["model_calls_successful"] += 1
            stats["briefs_generated"] += int(bool(enriched_item.opportunity_brief.owner_summary))
            stats["label_changes_after_extraction"] += int(
                bool(enriched_item.pre_extraction_label)
                and enriched_item.pre_extraction_label != enriched_item.label
            )
            enriched.append(enriched_item)
        except Exception:
            mode = "deterministic_fallback"
            _open_nim_circuit()
            stats["model_calls_failed"] += 1
            stats["model_calls_avoided_by_failure"] = top_count - stats["model_calls_attempted"]
            fallback = _fallback_enrich(profile, opportunities)
            stats["model_calls_successful"] = 0
            stats["label_changes_after_extraction"] = 0
            stats["briefs_generated"] = sum(
                1 for item in fallback if item.opportunity_brief.owner_summary
            )
            return _with_optional_stats(
                fallback,
                mode,
                stats,
                return_stats,
            )

    return _with_optional_stats(enriched, mode, stats, return_stats)


def _extract_with_nim(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
) -> tuple[RequirementExtraction, OpportunityBrief]:
    prompt = _structured_prompt(profile, opportunity)
    try:
        content = _chat_completion(prompt, with_schema=True)
    except SchemaRejectedError:
        content = _chat_completion(prompt, with_schema=False)
    payload = _extract_json_object(content)
    return _validate_extraction(payload, source="local_nim"), _validate_brief(payload, source="local_nim")


def _chat_completion(prompt: str, with_schema: bool) -> str:
    payload: dict[str, Any] = {
        "model": os.environ.get("NIM_MODEL", DEFAULT_MODEL),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You extract procurement requirements for a local bid intelligence system. "
                    "Use only the supplied evidence. Return JSON only. Do not make the final "
                    "bid/no-bid decision; extract facts, risks, questions, and owner-ready draft "
                    "language grounded in the supplied evidence."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 1500,
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
            raise SchemaRejectedError("NIM endpoint rejected response_format") from exc
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
    brief: OpportunityBrief,
) -> EvaluatedOpportunity:
    reconciled = _reconcile_extraction(profile, opportunity, extraction, brief)
    if extraction.source == "local_nim":
        reconciled = _with_owner_brief_rationale(reconciled, brief, extraction)
    return replace(
        reconciled,
        pre_extraction_label=opportunity.label,
        requirements=extraction,
        opportunity_brief=brief,
        nemotron_summary=_summary_from_requirements(profile, reconciled, extraction),
    )


def _with_owner_brief_rationale(
    opportunity: EvaluatedOpportunity,
    brief: OpportunityBrief,
    extraction: RequirementExtraction,
) -> EvaluatedOpportunity:
    final_rationale = _brief_final_rationale(opportunity, brief, extraction)
    if not final_rationale:
        return opportunity

    trace = opportunity.bid_fitness_trace
    positive_signals = list(trace.positive_signals)
    fit_reason = _short_text(brief.fit_reason, limit=420)
    if fit_reason and fit_reason not in positive_signals:
        positive_signals.insert(0, fit_reason)

    updated_trace = replace(
        trace,
        positive_signals=_unique_strings(positive_signals),
        final_rationale=final_rationale,
    )
    return replace(opportunity, bid_fitness_trace=updated_trace)


def _brief_final_rationale(
    opportunity: EvaluatedOpportunity,
    brief: OpportunityBrief,
    extraction: RequirementExtraction,
) -> str:
    label = opportunity.label
    summary = _sentence_fragment(_short_text(brief.owner_summary, limit=260))
    fit_reason = _sentence_fragment(_short_text(brief.fit_reason, limit=420))
    next_step = _sentence_fragment(_short_text(
        (brief.next_steps[0] if brief.next_steps else extraction.next_action),
        limit=140,
    ))
    concern = _sentence_fragment(_short_text(
        (brief.blockers or brief.missing_items or extraction.risk_flags or extraction.capacity_flags or [""])[0],
        limit=120,
    ))

    if label == "Skip":
        reason = concern or summary or fit_reason
        return f"Skip: {reason}." if reason else ""
    if label == "Review" and concern:
        body = summary or fit_reason or "the local brief found a concern to check"
        return f"Review: {concern}. {body}."
    body = fit_reason or summary
    if body and next_step:
        return f"{label}: {body}. Next step: {next_step}."
    if body:
        return f"{label}: {body}."
    if next_step:
        return f"{label}: {next_step}."
    return ""


def _sentence_fragment(value: str) -> str:
    return value.strip().rstrip(".;:")


def _with_fallback_requirements(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
) -> EvaluatedOpportunity:
    extraction = _fallback_extraction(profile, opportunity)
    brief = _fallback_brief(profile, opportunity, extraction)
    return _with_extraction(profile, opportunity, extraction, brief)


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
    delivery_complexity = _delivery_complexity(opportunity, risk_flags)
    scope_size = _scope_size(opportunity)
    next_action = _next_action(opportunity, risk_flags, capacity_flags)
    procurement_type = solicitation.solicitation_type or "Solicitation"
    summary_services = list(opportunity.matched_terms[:3]) or services
    summary = _compact_summary(solicitation, summary_services, risk_flags, capacity_flags, deadline_risk)
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
        delivery_complexity=delivery_complexity,
        scope_size=scope_size,
        disqualifying_requirements=list(opportunity.rejection_reasons[:5]),
        next_action=next_action,
        summary=summary,
    )


def _fallback_brief(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    extraction: RequirementExtraction,
) -> OpportunityBrief:
    source = extraction.source
    missing = _unique_strings(opportunity.missing_requirements + extraction.capacity_flags)
    required_documents = _unique_strings(extraction.documents or profile.ready_documents[:4])
    blockers = _unique_strings(opportunity.rejection_reasons + extraction.risk_flags)
    questions = _fallback_questions(opportunity, extraction)
    next_steps = _fallback_next_steps(opportunity, extraction, missing)
    owner_summary = extraction.summary or _compact_summary(
        opportunity.solicitation,
        extraction.services or opportunity.matched_terms,
        extraction.risk_flags,
        extraction.capacity_flags,
        extraction.deadline_risk,
    )
    fit_reason = _fit_reason(profile, opportunity, extraction)
    return OpportunityBrief(
        source=source,
        owner_summary=owner_summary,
        fit_reason=fit_reason,
        blockers=blockers,
        required_documents=required_documents,
        missing_items=missing,
        clarification_questions=questions,
        next_steps=next_steps,
        buyer_email_draft=_fallback_email_draft(profile, opportunity, extraction, owner_ready=False),
    )


def _reconcile_extraction(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    extraction: RequirementExtraction,
    brief: OpportunityBrief,
) -> EvaluatedOpportunity:
    requirement_signals = _brief_requirement_signals(extraction, brief)
    if extraction.source != "local_nim":
        return _with_trace_enrichment(opportunity, requirement_signals, [], [], "deterministic extraction")

    missing = _unique_strings(opportunity.missing_requirements + brief.missing_items)
    review_risks = _unique_strings(brief.blockers + extraction.risk_flags + extraction.capacity_flags)
    label = opportunity.label
    reasons = list(opportunity.reasons)
    rejection_reasons = list(opportunity.rejection_reasons)
    soft_warnings: list[str] = []
    rules = ["Nemotron extraction reconciliation rule"]

    if label == "Pursue" and review_risks:
        label = "Review"
        warning = f"Nemotron extracted owner-review risk: {review_risks[0]}."
        soft_warnings.append(warning)
        reasons.append("Nemotron extracted a risk that requires owner review before pursuit.")
    if label != "Skip" and missing:
        soft_warnings.append(f"Nemotron missing-item review: {', '.join(missing[:3])}.")
        reasons.append("Nemotron extracted missing packet items for owner confirmation.")
    if label != "Skip" and _requires_owner_review(profile, review_risks):
        label = "Review"
        rejection_reasons.append("nemotron blocker requires owner review")

    capacity_assessment = opportunity.capacity_assessment
    if label == "Review" and opportunity.label == "Pursue":
        capacity_assessment = replace(
            capacity_assessment,
            recommended_action="Pursue After Review",
            warnings=_unique_strings(
                capacity_assessment.warnings
                + ["Nemotron brief found risks or missing items that require owner review."]
            ),
        )

    reconciled = replace(
        opportunity,
        label=label,
        missing_requirements=missing,
        rejection_reasons=sorted(set(rejection_reasons)),
        reasons=_unique_strings(reasons),
        capacity_assessment=capacity_assessment,
    )
    return _with_trace_enrichment(reconciled, requirement_signals, soft_warnings, rules, "local Nemotron")


def _with_trace_enrichment(
    opportunity: EvaluatedOpportunity,
    requirement_signals: list[str],
    soft_warnings: list[str],
    rules: list[str],
    source_label: str,
) -> EvaluatedOpportunity:
    trace = opportunity.bid_fitness_trace
    final_rationale = trace.final_rationale
    if soft_warnings and opportunity.label == "Review":
        final_rationale = f"Review: {soft_warnings[0].rstrip('.')}. Final decision still follows the bid-fitness policy."
    elif requirement_signals and not final_rationale:
        final_rationale = f"{opportunity.label}: extracted requirements came from {source_label}."
    updated_trace = replace(
        trace,
        soft_warnings=_unique_strings(trace.soft_warnings + soft_warnings),
        requirement_signals=_unique_strings(trace.requirement_signals + requirement_signals),
        rules_triggered=_unique_strings(trace.rules_triggered + rules),
        final_rationale=final_rationale,
    )
    return replace(opportunity, bid_fitness_trace=updated_trace)


def _requires_owner_review(profile: BusinessProfile, risks: list[str]) -> bool:
    lowered = " ".join(risks).lower()
    if not lowered:
        return False
    review_terms = ("mandatory", "not eligible", "bond", "insurance", "wsib", "license", "capacity")
    profile_exclusions = [item.lower() for item in profile.missing_capabilities]
    return any(term in lowered for term in review_terms) or any(
        item and item in lowered for item in profile_exclusions
    )


def _brief_requirement_signals(
    extraction: RequirementExtraction,
    brief: OpportunityBrief,
) -> list[str]:
    signals: list[str] = []
    for label, values in (
        ("Extracted services", extraction.services),
        ("Required documents", brief.required_documents or extraction.documents),
        ("Clarification questions", brief.clarification_questions),
        ("Brief next steps", brief.next_steps),
    ):
        cleaned = _unique_strings(values)
        if cleaned:
            signals.append(f"{label}: {', '.join(cleaned[:4])}.")
    if brief.fit_reason:
        signals.append(f"Owner fit reason: {brief.fit_reason}.")
    return _unique_strings(signals)


def _fallback_questions(
    opportunity: EvaluatedOpportunity,
    extraction: RequirementExtraction,
) -> list[str]:
    questions = []
    if not extraction.documents:
        questions.append("Which insurance, WSIB, bonding, and portal forms are mandatory for this solicitation?")
    if extraction.deadline_risk in {"Tight", "Critical", "Unknown"}:
        questions.append("Are there addenda, mandatory meetings, or deadline details the vendor should confirm?")
    if extraction.risk_flags or extraction.capacity_flags:
        questions.append("Can the buyer clarify scope, site count, and any capacity-sensitive delivery requirements?")
    return questions[:3]


def _fallback_next_steps(
    opportunity: EvaluatedOpportunity,
    extraction: RequirementExtraction,
    missing: list[str],
) -> list[str]:
    steps = [
        "Open the official Toronto bidding portal record and confirm the full solicitation package.",
        extraction.next_action or _next_action(opportunity, extraction.risk_flags, extraction.capacity_flags),
    ]
    if missing:
        steps.append("Resolve missing or uncertain packet items: " + ", ".join(missing[:4]) + ".")
    else:
        steps.append("Confirm ready documents against the official package before owner approval.")
    return _unique_strings(steps)


def _fit_reason(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    extraction: RequirementExtraction,
) -> str:
    services = extraction.services or opportunity.matched_terms
    history = opportunity.historical
    assessment = opportunity.capacity_assessment
    parts: list[str] = []
    if services:
        parts.append(
            f"{profile.name} already has capability signals for {_human_join(services[:4])}, "
            "which line up with the listed scope."
        )
    else:
        parts.append(f"{profile.name} matches this opportunity through the selected {profile.label} profile.")
    if history.similar_count:
        parts.append(
            f"The local award comparison found {history.similar_count} similar Toronto award(s)"
            f"{f' with a median award around ${history.award_median:,.0f}' if history.award_median else ''}, "
            "so the recommendation is grounded in past purchasing patterns instead of keyword overlap."
        )
    if assessment:
        parts.append(
            f"Capacity check shows {assessment.pursuit_load.lower()} pursuit load, "
            f"{assessment.response_capacity.lower()}, and {assessment.execution_capacity.lower()}."
        )
    return " ".join(parts)


def _fallback_email_draft(
    profile: BusinessProfile,
    opportunity: EvaluatedOpportunity,
    extraction: RequirementExtraction,
    owner_ready: bool,
) -> str:
    buyer_name = opportunity.solicitation.buyer_name or "Procurement Team"
    document_number = opportunity.solicitation.document_number or "the solicitation"
    if not owner_ready:
        return (
            "Owner-ready buyer email requires a local Nemotron brief. Start local NIM/Nemotron, "
            "rerun the scan, and approve again to generate grounded outreach text."
        )
    services = _human_join((extraction.services or opportunity.matched_terms)[:4]) or profile.business_type
    return (
        f"Subject: Clarification for {document_number}\n\n"
        f"Hello {buyer_name},\n\n"
        f"{profile.name} is reviewing {document_number}. We provide {services} in Toronto and "
        "would like to confirm any mandatory documents, addenda, or site requirements before "
        "finalizing our response.\n\n"
        f"Thank you,\n{profile.name}"
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
                "summary": (
                    "one plain-English sentence describing the work for an owner; avoid copying "
                    "the solicitation description, avoid sales language, and use only supplied evidence"
                ),
                "owner_brief": {
                    "owner_summary": "one or two owner-facing sentences explaining the opportunity",
                    "fit_reason": (
                        "2-4 plain-English sentences explaining why this exact business profile is a fit. "
                        "Mention matched services, relevant capacity, historical award evidence, and any caveat "
                        "that still needs owner review. This should help a non-procurement owner understand the "
                        "fit in under 10 seconds."
                    ),
                    "blockers": "explicit blockers or risks the owner must resolve before pursuing",
                    "required_documents": "documents likely needed for the packet",
                    "missing_items": "items the profile may not currently have ready",
                    "clarification_questions": "buyer questions grounded in ambiguity from the solicitation",
                    "next_steps": "concrete owner workflow steps before submission",
                    "buyer_email_draft": (
                        "short professional email draft to the listed buyer; do not claim submission, "
                        "approval, or qualifications not supplied"
                    ),
                },
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
        delivery_complexity=_short_text(payload.get("delivery_complexity"), limit=80),
        scope_size=_short_text(payload.get("scope_size"), limit=80),
        disqualifying_requirements=_string_list(payload.get("disqualifying_requirements")),
        next_action=_short_text(payload.get("next_action"), limit=160),
        summary=_short_text(payload.get("summary"), limit=240),
    )


def _validate_brief(payload: dict[str, Any], source: str) -> OpportunityBrief:
    raw_brief = payload.get("owner_brief") if isinstance(payload.get("owner_brief"), dict) else {}
    required_documents = _string_list(raw_brief.get("required_documents"))
    if not required_documents:
        required_documents = _string_list(payload.get("documents"))
    owner_summary = _short_text(raw_brief.get("owner_summary"), limit=420)
    if not owner_summary:
        owner_summary = _short_text(payload.get("summary"), limit=420)
    return OpportunityBrief(
        source=source,
        owner_summary=owner_summary,
        fit_reason=_short_text(raw_brief.get("fit_reason"), limit=700),
        blockers=_string_list(raw_brief.get("blockers")),
        required_documents=required_documents,
        missing_items=_string_list(raw_brief.get("missing_items")),
        clarification_questions=_string_list(raw_brief.get("clarification_questions"), limit=5),
        next_steps=_string_list(raw_brief.get("next_steps"), limit=5),
        buyer_email_draft=_short_text(raw_brief.get("buyer_email_draft"), limit=900),
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
    plain_summary = _plain_owner_summary(opportunity, extraction)
    return (
        f"{opportunity.label}: {plain_summary} "
        f"For {profile.name}, extracted services are {services}. "
        f"Risks: {risks}. Historical signal: {award_signal}. Next action: {next_action}."
    )


def _plain_owner_summary(
    opportunity: EvaluatedOpportunity,
    extraction: RequirementExtraction,
) -> str:
    candidate = str(extraction.summary or "").strip()
    official = str(opportunity.solicitation.description or "").strip()
    if candidate:
        candidate_key = candidate.lower()
        official_key = official.lower()
        if not official_key or (candidate_key != official_key and official_key not in candidate_key):
            return candidate
    return _compact_summary(
        opportunity.solicitation,
        extraction.services or opportunity.matched_terms,
        extraction.risk_flags,
        extraction.capacity_flags,
        extraction.deadline_risk or _deadline_risk(opportunity.days_until_deadline),
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


def _delivery_complexity(opportunity: EvaluatedOpportunity, risk_flags: list[str]) -> str:
    if opportunity.capacity_assessment.execution_capacity == "Likely Too Large":
        return "High"
    if risk_flags or opportunity.capacity_assessment.execution_capacity == "Needs Scheduling Review":
        return "Medium"
    return "Low"


def _scope_size(opportunity: EvaluatedOpportunity) -> str:
    value = opportunity.historical.award_median or opportunity.historical.award_max
    if value >= 1000000:
        return "Large"
    if value >= 250000:
        return "Medium"
    if value > 0:
        return "Small"
    return "Unknown"


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
    solicitation: Any,
    services: list[str],
    risk_flags: list[str],
    capacity_flags: list[str],
    deadline_risk: str,
) -> str:
    service_text = _human_join(services[:3]) if services else ""
    if service_text:
        scope = f"{service_text} work"
    else:
        category = str(getattr(solicitation, "category", "") or "").strip().lower()
        scope = f"{category} work" if category else "City procurement work"
    division = str(getattr(solicitation, "division", "") or "").strip()
    buyer_text = f" for {division}" if division else ""
    risks = risk_flags + capacity_flags
    risk_text = _human_join(risks[:2]) if risks else "no major blocker surfaced"
    deadline_text = {
        "Critical": "the response window looks critical",
        "Tight": "the response window looks tight",
        "Manageable": "the response window looks manageable",
        "Unknown": "the deadline needs confirmation",
    }.get(deadline_risk, "the deadline needs confirmation")
    return f"This is {scope}{buyer_text}; {risk_text}; {deadline_text}."


def _human_join(items: list[str]) -> str:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


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


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        text = _short_text(value, limit=180)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


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
        "model_calls_successful": 0,
        "model_calls_failed": 0,
        "briefs_generated": 0,
        "label_changes_after_extraction": 0,
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
    if os.environ.get("CONTRACT_RADAR_DISABLE_NEMOTRON") == "1":
        return {"available": False, "reason": "disabled_by_flag", "base_url": base_url}

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
    models_url = f"{base_url}/models"
    req = request.Request(models_url, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as response:
            if 200 <= response.status < 300:
                result = {
                    "available": True,
                    "reason": "http_ready",
                    "base_url": base_url,
                    "models_url": models_url,
                    "host": host,
                    "port": port,
                }
                _cache_nim_preflight(cache_key, result)
                return result
            detail = f"HTTP {response.status}"
    except error.HTTPError as exc:
        detail = f"HTTP {exc.code}"
    except (error.URLError, TimeoutError, OSError) as exc:
        detail = str(exc)[:120]

    result = {
        "available": False,
        "reason": "http_preflight_failed",
        "base_url": base_url,
        "models_url": models_url,
        "host": host,
        "port": port,
        "detail": detail,
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
