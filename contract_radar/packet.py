from __future__ import annotations

from typing import Any

from contract_radar.models import ApprovalPacket, BusinessProfile, OpportunityBrief


def create_approval_packet(
    business_profile: BusinessProfile | dict[str, Any],
    opportunity: Any,
    approved: bool,
) -> ApprovalPacket:
    """Build a bid packet only after explicit owner approval."""
    profile = _as_profile(business_profile)
    solicitation = _value(opportunity, "solicitation", {}) or {}
    opportunity_id = str(_value(solicitation, "document_number") or "unknown-opportunity")
    title = str(_value(solicitation, "description") or opportunity_id)
    label = str(_value(opportunity, "label", "Monitor"))
    matched_terms = [str(item) for item in (_value(opportunity, "matched_terms", []) or [])]
    missing_requirements = [str(item) for item in (_value(opportunity, "missing_requirements", []) or [])]
    deadline = _value(solicitation, "submission_deadline")
    brief = _opportunity_brief(opportunity)
    requirements = _value(opportunity, "requirements", {}) or _value(opportunity, "nemotron_requirements", {}) or {}
    extraction_source = str(_value(brief, "source") or _value(requirements, "source") or "deterministic_fallback")
    owner_ready = approved and extraction_source == "local_nim"
    requires_nemotron = approved and not owner_ready

    checklist = _base_checklist(
        profile=profile,
        deadline=deadline,
        missing_requirements=_unique(missing_requirements + _list_value(brief, "missing_items")),
        required_documents=_list_value(brief, "required_documents"),
        next_steps=_list_value(brief, "next_steps"),
        owner_ready=owner_ready,
    )
    simulated_receipt = ""
    if owner_ready:
        checklist.extend(
            [
                "Confirm final pricing and availability for the response window.",
                "Upload required documents in SAP Ariba.",
                "Submit the response before the posted deadline.",
            ]
        )
        simulated_receipt = f"SIM-{opportunity_id}-{profile.name.replace(' ', '').upper()}"
    elif requires_nemotron:
        checklist.insert(0, "Owner-ready packet blocked: start local Nemotron/NIM, rerun the scan, and approve again.")
    else:
        checklist.insert(0, "Owner approval required before any bid packet or simulated submission is prepared.")

    return ApprovalPacket(
        approved=approved,
        owner_ready=owner_ready,
        requires_nemotron=requires_nemotron,
        opportunity_id=opportunity_id,
        title=title,
        summary=_summary(profile, title, label, matched_terms, approved, brief, owner_ready),
        checklist=checklist,
        clarification_questions=_clarification_questions(brief, requires_nemotron),
        buyer_contact=_buyer_contact(solicitation),
        draft_email=_draft_email(profile, solicitation, title, matched_terms, approved, brief, owner_ready),
        sap_ariba_steps=_sap_ariba_steps(approved, owner_ready, requires_nemotron),
        simulated_receipt=simulated_receipt,
    )


def _summary(
    profile: BusinessProfile,
    title: str,
    label: str,
    matched_terms: list[str],
    approved: bool,
    brief: OpportunityBrief,
    owner_ready: bool,
) -> str:
    if approved and not owner_ready:
        return (
            f"{profile.name} has a ranked '{label}' opportunity for '{title}', but the owner-ready "
            "packet is blocked until local Nemotron generates a validated bid brief."
        )
    if owner_ready and brief.owner_summary:
        fit = f" {brief.fit_reason}" if brief.fit_reason else ""
        return f"{brief.owner_summary}{fit}".strip()
    terms = ", ".join(matched_terms[:5]) if matched_terms else profile.business_type
    approval_note = "The owner approved packet preparation." if approved else "The owner has not approved packet preparation yet."
    return (
        f"{profile.name} is marked '{label}' for '{title}' because it matches {terms}. "
        f"{approval_note}"
    )


def _base_checklist(
    profile: BusinessProfile,
    deadline: Any,
    missing_requirements: list[str],
    required_documents: list[str],
    next_steps: list[str],
    owner_ready: bool,
) -> list[str]:
    documents = required_documents or profile.ready_documents
    checklist = [
        f"Verify {profile.name}'s service capacity for this opportunity.",
        "Review the solicitation document and addenda in the official Toronto bidding portal.",
        "Attach required documents: " + ", ".join(documents) + ".",
    ]
    if deadline:
        checklist.append(f"Calendar the submission deadline: {deadline}.")
    if missing_requirements:
        checklist.append("Resolve missing requirements: " + ", ".join(missing_requirements) + ".")
    else:
        checklist.append("No missing requirements were flagged by the current scan.")
    if owner_ready:
        checklist.extend(next_steps[:4])
    return _unique(checklist)


def _buyer_contact(solicitation: Any) -> dict[str, str]:
    return {
        "name": str(_value(solicitation, "buyer_name") or "Not listed"),
        "email": str(_value(solicitation, "buyer_email") or "Not listed"),
        "phone": str(_value(solicitation, "buyer_phone") or "Not listed"),
        "division": str(_value(solicitation, "division") or "Not listed"),
    }


def _draft_email(
    profile: BusinessProfile,
    solicitation: Any,
    title: str,
    matched_terms: list[str],
    approved: bool,
    brief: OpportunityBrief,
    owner_ready: bool,
) -> str:
    if approved and not owner_ready:
        return (
            "Owner-ready buyer email requires a local Nemotron brief. Start local NIM/Nemotron, "
            "rerun the scan, and approve again to generate grounded outreach text."
        )
    if owner_ready and brief.buyer_email_draft:
        return brief.buyer_email_draft
    buyer_name = _value(solicitation, "buyer_name") or "Procurement Team"
    document_number = _value(solicitation, "document_number") or "the solicitation"
    capability_line = ", ".join(matched_terms[:5]) if matched_terms else profile.business_type
    status_line = (
        "We are preparing our response package"
        if approved
        else "Pending owner approval, we are reviewing whether to prepare a response package"
    )
    return (
        f"Subject: Interest in {document_number}\n\n"
        f"Hello {buyer_name},\n\n"
        f"{status_line} for {title}. {profile.name} provides {capability_line} in Toronto "
        f"with a team size of {profile.team_size} and service capacity of up to "
        f"{profile.max_sites_per_day} city site(s) per day.\n\n"
        "Please let us know if there are addenda or mandatory details we should confirm before submission.\n\n"
        f"Thank you,\n{profile.name}"
    )


def _sap_ariba_steps(approved: bool, owner_ready: bool, requires_nemotron: bool) -> list[str]:
    if requires_nemotron:
        return [
            "Start or reconnect local Nemotron/NIM.",
            "Rerun the scan so the shortlisted opportunity gets a validated bid brief.",
            "Approve again after the owner-ready checklist and buyer questions are generated.",
        ]
    steps = [
        "Log in to the City of Toronto SAP Ariba supplier portal.",
        "Search for the solicitation document number.",
        "Download the official documents and review all addenda.",
    ]
    if approved and owner_ready:
        steps.extend(
            [
                "Complete the response forms using the approved packet.",
                "Upload attachments and submit through SAP Ariba.",
                "Save the confirmation number with the simulated receipt for demo tracking.",
            ]
        )
    else:
        steps.append("Wait for owner approval before preparing or submitting response materials.")
    return steps


def _as_profile(profile: BusinessProfile | dict[str, Any]) -> BusinessProfile:
    if isinstance(profile, BusinessProfile):
        return profile
    return BusinessProfile.from_payload(profile if isinstance(profile, dict) else {})


def _opportunity_brief(opportunity: Any) -> OpportunityBrief:
    raw = _value(opportunity, "opportunity_brief", None) or _value(opportunity, "nemotron_brief", None) or {}
    if isinstance(raw, OpportunityBrief):
        return raw
    if not isinstance(raw, dict):
        raw = {}
    return OpportunityBrief(
        source=str(raw.get("source") or "deterministic_fallback"),
        owner_summary=str(raw.get("owner_summary") or ""),
        fit_reason=str(raw.get("fit_reason") or ""),
        blockers=[str(item) for item in raw.get("blockers") or [] if str(item).strip()],
        required_documents=[str(item) for item in raw.get("required_documents") or [] if str(item).strip()],
        missing_items=[str(item) for item in raw.get("missing_items") or [] if str(item).strip()],
        clarification_questions=[str(item) for item in raw.get("clarification_questions") or [] if str(item).strip()],
        next_steps=[str(item) for item in raw.get("next_steps") or [] if str(item).strip()],
        buyer_email_draft=str(raw.get("buyer_email_draft") or ""),
    )


def _list_value(source: Any, key: str) -> list[str]:
    value = _value(source, key, []) or []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _clarification_questions(brief: OpportunityBrief, requires_nemotron: bool) -> list[str]:
    if requires_nemotron:
        return ["Run local Nemotron to generate buyer clarification questions from the shortlisted contract."]
    return brief.clarification_questions


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        text = str(value or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)
