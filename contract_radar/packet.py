from __future__ import annotations

from typing import Any

from contract_radar.models import ApprovalPacket, BusinessProfile


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

    checklist = _base_checklist(profile, deadline, missing_requirements)
    simulated_receipt = ""
    if approved:
        checklist.extend(
            [
                "Confirm final pricing and availability for the response window.",
                "Upload required documents in SAP Ariba.",
                "Submit the response before the posted deadline.",
            ]
        )
        simulated_receipt = f"SIM-{opportunity_id}-{profile.name.replace(' ', '').upper()}"
    else:
        checklist.insert(0, "Owner approval required before any bid packet or simulated submission is prepared.")

    return ApprovalPacket(
        approved=approved,
        opportunity_id=opportunity_id,
        title=title,
        summary=_summary(profile, title, label, matched_terms, approved),
        checklist=checklist,
        buyer_contact=_buyer_contact(solicitation),
        draft_email=_draft_email(profile, solicitation, title, matched_terms, approved),
        sap_ariba_steps=_sap_ariba_steps(approved),
        simulated_receipt=simulated_receipt,
    )


def _summary(
    profile: BusinessProfile,
    title: str,
    label: str,
    matched_terms: list[str],
    approved: bool,
) -> str:
    terms = ", ".join(matched_terms[:5]) if matched_terms else profile.business_type
    approval_note = "The owner approved packet preparation." if approved else "The owner has not approved packet preparation yet."
    return (
        f"{profile.name} is marked '{label}' for '{title}' because it matches {terms}. "
        f"{approval_note}"
    )


def _base_checklist(profile: BusinessProfile, deadline: Any, missing_requirements: list[str]) -> list[str]:
    checklist = [
        f"Verify {profile.name}'s service capacity for this opportunity.",
        "Review the solicitation document and addenda in the official Toronto bidding portal.",
        "Attach ready documents: " + ", ".join(profile.ready_documents) + ".",
    ]
    if deadline:
        checklist.append(f"Calendar the submission deadline: {deadline}.")
    if missing_requirements:
        checklist.append("Resolve missing requirements: " + ", ".join(missing_requirements) + ".")
    else:
        checklist.append("No missing requirements were flagged by the current scan.")
    return checklist


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
) -> str:
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


def _sap_ariba_steps(approved: bool) -> list[str]:
    steps = [
        "Log in to the City of Toronto SAP Ariba supplier portal.",
        "Search for the solicitation document number.",
        "Download the official documents and review all addenda.",
    ]
    if approved:
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


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)
