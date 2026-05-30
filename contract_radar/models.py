from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


FIT_LABELS = ("Pursue", "Review", "Monitor", "Skip")


def parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def money_to_float(value: Any) -> float:
    text = str(value or "").replace("$", "").replace(",", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


@dataclass
class BusinessProfile:
    name: str = "GTA Mechanical & Controls Ltd."
    business_type: str = "commercial HVAC, building automation, and mechanical contractor"
    base_location: str = "Toronto, Ontario"
    team_size: int = 12
    max_contract_value: float = 350000.0
    max_sites_per_day: int = 5
    active_pursuit_count: int = 0
    max_active_pursuits: int = 3
    service_area: str = "Toronto"
    skills: list[str] = field(
        default_factory=lambda: [
            "HVAC maintenance",
            "building automation systems/BAS controls",
            "boiler service",
            "chiller service",
            "emergency repairs",
            "preventative maintenance",
            "energy retrofit support",
            "municipal/public facility service",
            "mechanical repairs",
        ]
    )
    ready_documents: list[str] = field(
        default_factory=lambda: [
            "insurance",
            "WSIB",
            "HST",
            "references",
            "technician certifications",
        ]
    )
    missing_capabilities: list[str] = field(
        default_factory=lambda: [
            "major design/build construction",
            "large construction bonding",
            "kitchen equipment",
            "road paving",
            "pure software implementation",
            "food supply",
        ]
    )
    response_days_available: int = 10

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "BusinessProfile":
        payload = payload or {}
        profile = cls()
        for field_name in (
            "name",
            "business_type",
            "base_location",
            "service_area",
        ):
            if payload.get(field_name):
                setattr(profile, field_name, str(payload[field_name]))
        for field_name in (
            "team_size",
            "max_sites_per_day",
            "response_days_available",
            "active_pursuit_count",
            "max_active_pursuits",
        ):
            if payload.get(field_name) is not None:
                minimum = 0 if field_name == "active_pursuit_count" else 1
                setattr(profile, field_name, max(minimum, int(payload[field_name])))
        if payload.get("max_contract_value") is not None:
            profile.max_contract_value = max(0.0, float(payload["max_contract_value"]))
        for field_name in ("skills", "ready_documents", "missing_capabilities"):
            if isinstance(payload.get(field_name), list):
                setattr(profile, field_name, [str(item) for item in payload[field_name] if str(item).strip()])
        return profile

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Solicitation:
    document_number: str
    solicitation_type: str
    category: str
    description: str
    division: str
    issue_date: date | None
    submission_deadline: date | None
    buyer_name: str = ""
    buyer_email: str = ""
    buyer_phone: str = ""
    wards: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "Solicitation":
        return cls(
            document_number=str(record.get("Document Number") or record.get("document_number") or "").strip(),
            solicitation_type=str(record.get("RFx (Solicitation) Type") or record.get("solicitation_type") or ""),
            category=str(record.get("High Level Category") or record.get("category") or ""),
            description=str(
                record.get("Solicitation Document Description")
                or record.get("description")
                or ""
            ),
            division=str(record.get("Division") or record.get("division") or ""),
            issue_date=parse_date(record.get("Issue Date") or record.get("issue_date")),
            submission_deadline=parse_date(record.get("Submission Deadline") or record.get("submission_deadline")),
            buyer_name=str(record.get("Buyer Name") or record.get("buyer_name") or ""),
            buyer_email=str(record.get("Buyer Email") or record.get("buyer_email") or ""),
            buyer_phone=str(record.get("Buyer Phone Number") or record.get("buyer_phone") or ""),
            wards=str(record.get("Wards") or record.get("wards") or ""),
            raw=dict(record),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["issue_date"] = self.issue_date.isoformat() if self.issue_date else None
        data["submission_deadline"] = self.submission_deadline.isoformat() if self.submission_deadline else None
        return data


@dataclass
class AwardRecord:
    document_number: str
    solicitation_type: str
    category: str
    supplier: str
    award_value: float
    award_date: date | None
    division: str
    description: str
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> "AwardRecord":
        return cls(
            document_number=str(record.get("Document Number") or record.get("document_number") or ""),
            solicitation_type=str(record.get("RFx (Solicitation) Type") or record.get("solicitation_type") or ""),
            category=str(record.get("High Level Category") or record.get("category") or ""),
            supplier=str(record.get("Successful Supplier") or record.get("supplier") or ""),
            award_value=money_to_float(record.get("Award") or record.get("award_value")),
            award_date=parse_date(record.get("Award Authority Obtained Date") or record.get("award_date")),
            division=str(record.get("Division") or record.get("division") or ""),
            description=str(record.get("Solicitation Document Description") or record.get("description") or ""),
            raw=dict(record),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["award_date"] = self.award_date.isoformat() if self.award_date else None
        return data


@dataclass
class HistoricalComparison:
    similar_count: int = 0
    award_min: float = 0.0
    award_median: float = 0.0
    award_max: float = 0.0
    accessibility: str = "insufficient history"
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RequirementExtraction:
    source: str = "deterministic_fallback"
    services: list[str] = field(default_factory=list)
    certifications: list[str] = field(default_factory=list)
    documents: list[str] = field(default_factory=list)
    facility_signals: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    capacity_flags: list[str] = field(default_factory=list)
    procurement_type: str = ""
    deadline_risk: str = ""
    next_action: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CapacityAssessment:
    pursuit_load: str = "Clear"
    response_capacity: str = "Enough Time"
    execution_capacity: str = "Fits Team"
    recommended_action: str = "Monitor"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvaluatedOpportunity:
    solicitation: Solicitation
    label: str
    rank_score: int
    matched_terms: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    days_until_deadline: int | None = None
    historical: HistoricalComparison = field(default_factory=HistoricalComparison)
    requirements: RequirementExtraction = field(default_factory=RequirementExtraction)
    capacity_assessment: CapacityAssessment = field(default_factory=CapacityAssessment)
    nemotron_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["solicitation"] = self.solicitation.to_dict()
        data["historical"] = self.historical.to_dict()
        data["requirements"] = self.requirements.to_dict()
        data["nemotron_requirements"] = self.requirements.to_dict()
        return data


@dataclass
class PipelineMetrics:
    solicitations_loaded: int = 0
    awards_loaded: int = 0
    opportunities_evaluated: int = 0
    rejected_count: int = 0
    top_candidate_count: int = 0
    runtime_ms: int = 0
    records_per_second: float = 0.0
    shortlist_reduction_ratio: float = 0.0
    model_calls_attempted: int = 0
    model_calls_avoided: int = 0
    data_sources: dict[str, str] = field(default_factory=dict)
    label_counts: dict[str, int] = field(default_factory=dict)
    engine: str = "python"
    rapids_mode: str = "python_fallback"
    nemotron_mode: str = "deterministic_fallback"
    nvidia_stack_active: bool = False
    active_nvidia_tools: list[str] = field(default_factory=list)
    fetched_at: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ApprovalPacket:
    approved: bool
    opportunity_id: str
    title: str
    summary: str
    checklist: list[str]
    buyer_contact: dict[str, str]
    draft_email: str
    sap_ariba_steps: list[str]
    simulated_receipt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
