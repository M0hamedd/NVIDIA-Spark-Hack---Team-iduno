from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import urlencode

from contract_radar import config


FIT_LABELS = ("Pursue", "Review", "Monitor", "Skip")
TORONTO_BIDS_PORTAL_URL = (
    "https://www.toronto.ca/business-economy/doing-business-with-the-city/"
    "searching-bidding-on-city-contracts/toronto-bids-portal/"
)
TORONTO_BIDS_SEARCH_URL = f"{TORONTO_BIDS_PORTAL_URL}#all"


def source_links_for_solicitation(document_number: str, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    record = raw or {}
    document = str(document_number or "").strip()
    official_document = str(record.get("Document Number") or record.get("document_number") or "").strip()
    row_id = _row_id_value(record)
    is_demo_record = _is_demo_solicitation(document, record)
    links: dict[str, Any] = {
        "document_number": document,
        "source_label": "City of Toronto TO Bids",
        "toronto_bids_portal_url": TORONTO_BIDS_PORTAL_URL,
        "toronto_bids_search_url": TORONTO_BIDS_SEARCH_URL,
        "toronto_bids_search_hint": (
            f"Search {document} in TO Bids" if document else "Search by document number in TO Bids"
        ),
        "is_demo_record": is_demo_record,
    }

    if document and not is_demo_record:
        filters: dict[str, Any] = {"Document Number": official_document} if official_document else {}
        if not filters and row_id is not None:
            filters = {"_id": row_id}
        if filters:
            links["open_data_record_url"] = (
                f"{config.CKAN_DATASTORE_SEARCH_URL}?"
                f"{urlencode({'resource_id': config.SOLICITATIONS_RESOURCE_ID, 'filters': json.dumps(filters, separators=(',', ':'))})}"
            )
        if official_document:
            links["verification_note"] = (
                "Official Toronto Open Data record. Use this document number in the registered "
                "supplier workflow to inspect the full solicitation package."
            )
        elif row_id is not None:
            links["verification_note"] = (
                "Official Toronto Open Data row with no document number in the export. SoBid "
                "uses a stable row identifier so the end-to-end workflow can still track and verify it."
            )
        else:
            links["verification_note"] = (
                "Official Toronto Open Data record with no document number in the export. SoBid "
                "uses a stable fingerprint so the workflow can still track it."
            )
    elif is_demo_record:
        links["verification_note"] = (
            "Bundled dev fixture. Normal demo scans refuse these records and use Toronto Open Data only."
        )
    else:
        links["verification_note"] = "Use the buyer, title, or document number in the official supplier workflow."

    return links


def _is_demo_solicitation(document_number: str, raw: dict[str, Any]) -> bool:
    if raw.get("Demo Profile") or raw.get("Demo Role"):
        return True
    return document_number.startswith(("RFQ-2026-", "RFP-2026-", "RFQ-2025-", "RFP-2025-"))


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
    profile_id: str = "road_civil_infrastructure"
    label: str = "Road/Civil Infrastructure Contractor"
    name: str = "Harbourfront Civil Works Ltd."
    business_type: str = "road, sidewalk, bridge, sewer, watermain, paving, and civil infrastructure contractor"
    base_location: str = "Toronto, GTA"
    team_size: int = 28
    max_contract_value: float = 1800000.0
    max_sites_per_day: int = 4
    active_pursuit_count: int = 0
    max_active_pursuits: int = 3
    service_area: str = "Toronto"
    lane_basis: str = "2026 YTD Toronto solicitations: road, sidewalk, bridge, watermain, sewer, paving, and traffic infrastructure work."
    ytd_solicitation_hits: int = 45
    exclusive_best_fit_hits: int = 29
    top_divisions: list[str] = field(
        default_factory=lambda: [
            "Transportation Services",
            "Engineering & Construction Services",
            "Toronto Water",
        ]
    )
    good_fit_examples: list[str] = field(
        default_factory=lambda: [
            "road and sidewalk repair",
            "bridge rehabilitation",
            "watermain and sewer construction",
            "curb, asphalt, and traffic-stage civil work",
        ]
    )
    bad_fit_examples: list[str] = field(
        default_factory=lambda: [
            "pure software implementation",
            "parks-only landscaping",
            "professional design-only studies",
            "food or office supply",
        ]
    )
    skills: list[str] = field(
        default_factory=lambda: [
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
        ]
    )
    ready_documents: list[str] = field(
        default_factory=lambda: [
            "insurance",
            "WSIB",
            "HST",
            "bonding capacity",
            "municipal references",
            "traffic control plan",
        ]
    )
    missing_capabilities: list[str] = field(
        default_factory=lambda: [
            "professional engineering design only",
            "architectural consulting",
            "parks-only landscaping",
            "kitchen equipment",
            "pure software implementation",
            "food supply",
        ]
    )
    response_days_available: int = 14

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "BusinessProfile":
        payload = payload or {}
        profile = cls()
        for field_name in (
            "profile_id",
            "label",
            "name",
            "business_type",
            "base_location",
            "service_area",
            "lane_basis",
        ):
            if payload.get(field_name):
                setattr(profile, field_name, str(payload[field_name]))
        for field_name in (
            "team_size",
            "max_sites_per_day",
            "response_days_available",
            "active_pursuit_count",
            "max_active_pursuits",
            "ytd_solicitation_hits",
            "exclusive_best_fit_hits",
        ):
            if payload.get(field_name) is not None:
                minimum = 0 if field_name in {"active_pursuit_count", "ytd_solicitation_hits", "exclusive_best_fit_hits"} else 1
                setattr(profile, field_name, max(minimum, int(payload[field_name])))
        if payload.get("max_contract_value") is not None:
            profile.max_contract_value = max(0.0, float(payload["max_contract_value"]))
        for field_name in (
            "top_divisions",
            "good_fit_examples",
            "bad_fit_examples",
            "skills",
            "ready_documents",
            "missing_capabilities",
        ):
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
            document_number=_record_identifier(record, ("Document Number", "document_number"), "TOBIDS"),
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
        data["source_links"] = source_links_for_solicitation(self.document_number, self.raw)
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
            document_number=_record_identifier(record, ("Document Number", "document_number"), "TOAWARD"),
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


def _record_identifier(record: dict[str, Any], keys: tuple[str, ...], prefix: str) -> str:
    for key in keys:
        value = str(record.get(key) or "").strip()
        if value:
            return value
    row_id = _row_id_value(record)
    if row_id is not None:
        return f"{prefix}-ROW-{row_id}"
    digest = hashlib.sha256(_record_fingerprint(record).encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-ROW-{digest}"


def _row_id_value(record: dict[str, Any]) -> int | str | None:
    raw_value = record.get("_id")
    if raw_value is None:
        raw_value = record.get("id")
    text = str(raw_value or "").strip()
    if not text:
        return None
    return int(text) if text.isdigit() else text


def _record_fingerprint(record: dict[str, Any]) -> str:
    fields = (
        "Solicitation Document Description",
        "description",
        "RFx (Solicitation) Type",
        "solicitation_type",
        "High Level Category",
        "category",
        "Division",
        "division",
        "Submission Deadline",
        "submission_deadline",
        "Successful Supplier",
        "supplier",
        "Award",
        "award_value",
    )
    return "|".join(str(record.get(field) or "") for field in fields)


@dataclass
class HistoricalComparison:
    similar_count: int = 0
    award_min: float = 0.0
    award_median: float = 0.0
    award_max: float = 0.0
    accessibility: str = "insufficient history"
    evidence: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)

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
    delivery_complexity: str = ""
    scope_size: str = ""
    disqualifying_requirements: list[str] = field(default_factory=list)
    next_action: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class OpportunityBrief:
    source: str = "deterministic_fallback"
    owner_summary: str = ""
    fit_reason: str = ""
    blockers: list[str] = field(default_factory=list)
    required_documents: list[str] = field(default_factory=list)
    missing_items: list[str] = field(default_factory=list)
    clarification_questions: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    buyer_email_draft: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MarketFitSignal:
    source: str = "not_scored"
    score: float = 0.0
    confidence: str = "Unknown"
    summary: str = ""
    evidence: list[str] = field(default_factory=list)
    top_factors: list[dict[str, Any]] = field(default_factory=list)
    supplier_concentration: dict[str, Any] = field(default_factory=dict)
    model_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BidRecommendation:
    source: str = "not_estimated"
    recommended_bid: float = 0.0
    low_bid: float = 0.0
    high_bid: float = 0.0
    confidence: str = "Unknown"
    contract_type: str = ""
    historical_award_count: int = 0
    average_award: float = 0.0
    median_award: float = 0.0
    basis: str = ""
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PricingBreakdown:
    source: str = "not_priced"
    market_reference: float = 0.0
    direct_cost: float = 0.0
    contingency: float = 0.0
    overhead: float = 0.0
    margin: float = 0.0
    estimated_cost: float = 0.0
    cost_based_bid: float = 0.0
    market_adjusted_bid: float = 0.0
    recommended_bid: float = 0.0
    win_probability: float = 0.0
    expected_profit: float = 0.0
    bid_prep_cost: float = 0.0
    complexity_score: float = 0.0
    risk_multiplier: float = 1.0
    overhead_rate: float = 0.0
    margin_rate: float = 0.0
    contingency_rate: float = 0.0
    market_weight: float = 0.0
    cost_weight: float = 0.0
    candidate_bids: list[dict[str, Any]] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RAGEvidence:
    source: str = "not_retrieved"
    mode: str = "none"
    top_similarity: float = 0.0
    average_similarity: float = 0.0
    same_buyer_count: int = 0
    same_division_count: int = 0
    same_type_count: int = 0
    value_min: float = 0.0
    value_median: float = 0.0
    value_max: float = 0.0
    evidence: list[str] = field(default_factory=list)
    analogs: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationSummary:
    source: str = "not_simulated"
    seed: int = 0
    iterations: int = 0
    downside_case: float = 0.0
    likely_low: float = 0.0
    likely_high: float = 0.0
    upside_case: float = 0.0
    confidence: str = "Unknown"
    drivers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioDecision:
    source: str = "not_optimized"
    engine: str = "none"
    decision: str = "Monitor"
    priority_rank: int = 0
    expected_value: float = 0.0
    estimator_hours: float = 0.0
    capacity_used: bool = False
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelExplanation:
    source: str = "not_scored"
    model_type: str = ""
    feature_names: list[str] = field(default_factory=list)
    top_factors: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)

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
class BidFitnessTrace:
    hard_blockers: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)
    positive_signals: list[str] = field(default_factory=list)
    requirement_signals: list[str] = field(default_factory=list)
    historical_analogs: list[str] = field(default_factory=list)
    capacity_gates: list[str] = field(default_factory=list)
    scorecard_labels: dict[str, str] = field(default_factory=dict)
    rules_triggered: list[str] = field(default_factory=list)
    final_rationale: str = ""

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
    opportunity_brief: OpportunityBrief = field(default_factory=OpportunityBrief)
    market_fit: MarketFitSignal = field(default_factory=MarketFitSignal)
    bid_recommendation: BidRecommendation = field(default_factory=BidRecommendation)
    pricing_breakdown: PricingBreakdown = field(default_factory=PricingBreakdown)
    predicted_bid: float = 0.0
    bid_range_low: float = 0.0
    bid_range_high: float = 0.0
    fit_probability: float = 0.0
    revenue_score: float = 0.0
    risk_score: float = 0.0
    rag_evidence: RAGEvidence = field(default_factory=RAGEvidence)
    simulation_summary: SimulationSummary = field(default_factory=SimulationSummary)
    portfolio_decision: PortfolioDecision = field(default_factory=PortfolioDecision)
    model_explanation: ModelExplanation = field(default_factory=ModelExplanation)
    capacity_assessment: CapacityAssessment = field(default_factory=CapacityAssessment)
    bid_fitness_trace: BidFitnessTrace = field(default_factory=BidFitnessTrace)
    nemotron_summary: str = ""
    pre_extraction_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["solicitation"] = self.solicitation.to_dict()
        data["historical"] = self.historical.to_dict()
        data["requirements"] = self.requirements.to_dict()
        data["nemotron_requirements"] = self.requirements.to_dict()
        data["opportunity_brief"] = self.opportunity_brief.to_dict()
        data["nemotron_brief"] = self.opportunity_brief.to_dict()
        data["market_fit"] = self.market_fit.to_dict()
        data["bid_recommendation"] = self.bid_recommendation.to_dict()
        data["pricing_breakdown"] = self.pricing_breakdown.to_dict()
        data["rag_evidence"] = self.rag_evidence.to_dict()
        data["simulation_summary"] = self.simulation_summary.to_dict()
        data["portfolio_decision"] = self.portfolio_decision.to_dict()
        data["model_explanation"] = self.model_explanation.to_dict()
        data["capacity_assessment"] = self.capacity_assessment.to_dict()
        data["bid_fitness_trace"] = self.bid_fitness_trace.to_dict()
        data["label_changed_by_extraction"] = bool(
            self.pre_extraction_label and self.pre_extraction_label != self.label
        )
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
    model_calls_successful: int = 0
    model_calls_avoided: int = 0
    briefs_generated: int = 0
    label_changes_after_extraction: int = 0
    market_model_mode: str = "not_scored"
    market_model_examples: int = 0
    market_model_positive_examples: int = 0
    market_model_precision_at_10: float = 0.0
    market_model_top_decile_lift: float = 0.0
    market_model_average_precision: float = 0.0
    value_model_mode: str = "not_scored"
    value_model_mae: float = 0.0
    value_model_mape: float = 0.0
    rag_mode: str = "not_retrieved"
    cuopt_mode: str = "greedy_fallback"
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
    owner_ready: bool
    requires_nemotron: bool
    opportunity_id: str
    title: str
    summary: str
    checklist: list[str]
    clarification_questions: list[str]
    buyer_contact: dict[str, str]
    draft_email: str
    sap_ariba_steps: list[str]
    simulated_receipt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
