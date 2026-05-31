from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from statistics import median
from typing import Any

from contract_radar.models import AwardRecord, BusinessProfile, HistoricalComparison, Solicitation


COMPLEX_PAST_SCOPE_TERMS = {
    "bonding",
    "construction management",
    "design build",
    "design-build",
    "engineering services",
    "general contractor",
    "major construction",
    "prime contractor",
}

AWARD_BUYER_FIELDS = (
    "Buyer Name",
    "buyer_name",
    "Buyer",
    "buyer",
    "Buyer Contact",
    "buyer_contact",
    "Department",
    "department",
)


STOP_WORDS = {
    "and",
    "the",
    "for",
    "this",
    "that",
    "but",
    "with",
    "from",
    "city",
    "toronto",
    "services",
    "service",
    "supply",
    "delivery",
    "request",
    "quotation",
    "proposal",
    "tender",
    "contract",
    "maintenance",
    "repair",
    "all",
    "include",
    "includes",
    "including",
    "limited",
    "general",
    "scope",
    "work",
    "bid",
    "bids",
    "prospective",
    "supplier",
    "suppliers",
    "submit",
    "submitted",
    "labour",
    "labor",
    "materials",
    "material",
    "equipment",
    "necessary",
    "various",
    "exclusive",
    "non",
    "not",
    "provide",
    "provision",
    "locations",
    "throughout",
    "invitation",
    "rfq",
    "rfp",
    "rft",
    "rfsq",
    "deliverable",
    "deliverables",
    "specification",
    "specifications",
    "requirement",
    "requirements",
    "document",
    "documents",
    "part",
    "listed",
    "pricing",
    "form",
    "area",
    "areas",
    "posting",
    "ariba",
    "non-exclusive",
    "nonexclusive",
}


@dataclass
class HistoricalOpportunitySummary:
    realistic_count: int = 0
    sample_awards: list[dict[str, Any]] = field(default_factory=list)
    award_value_range: dict[str, float | int] = field(default_factory=dict)
    common_divisions: list[dict[str, Any]] = field(default_factory=list)
    common_buyers: list[dict[str, Any]] = field(default_factory=list)
    evidence_terms: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_past_opportunities(
    profile: BusinessProfile,
    awards: list[AwardRecord],
    sample_limit: int = 5,
) -> HistoricalOpportunitySummary:
    """Summarize past awarded contracts this business could realistically have pursued."""

    matches: list[tuple[int, AwardRecord, list[str]]] = []

    for award in awards:
        score, evidence_terms = _profile_award_fit(profile, award)
        if score > 0:
            matches.append((score, award, evidence_terms))

    matches.sort(
        key=lambda item: (
            item[0],
            item[1].award_value,
            item[1].award_date.isoformat() if item[1].award_date else "",
            item[1].document_number,
        ),
        reverse=True,
    )

    values = sorted(award.award_value for _, award, _ in matches if award.award_value > 0)
    divisions = _top_counts(award.division for _, award, _ in matches)
    buyers = _top_counts(_buyer_name(award) for _, award, _ in matches)
    evidence_terms = _top_terms(term for _, _, terms in matches for term in terms)
    sample_awards = [_sample_award_dict(award, terms) for _, award, terms in matches[:sample_limit]]

    evidence = _summary_evidence(len(matches), values, divisions, buyers, evidence_terms)

    return HistoricalOpportunitySummary(
        realistic_count=len(matches),
        sample_awards=sample_awards,
        award_value_range=_award_value_range(values),
        common_divisions=divisions,
        common_buyers=buyers,
        evidence_terms=evidence_terms,
        evidence=evidence,
    )


def compare_history(
    solicitation: Solicitation,
    awards: list[AwardRecord],
    profile: BusinessProfile,
) -> HistoricalComparison:
    """Compare a solicitation with historical awards using deterministic evidence."""

    solicitation_terms = meaningful_terms(_text_for(solicitation))
    similar: list[tuple[int, AwardRecord, list[str]]] = []

    for award in awards:
        if award.award_value <= 0:
            continue
        profile_score, _ = _profile_award_fit(profile, award)
        if profile_score <= 0:
            continue
        score, evidence_terms = _similarity_score(solicitation, award, solicitation_terms)
        service_evidence = [term for term in evidence_terms if term not in {"category", "solicitation type", "division"}]
        if score >= 5 and len(service_evidence) >= 2:
            similar.append((score, award, evidence_terms))

    if not similar:
        return HistoricalComparison(
            accessibility="insufficient history",
            evidence=["No sufficiently similar awarded contracts were found."],
        )

    similar.sort(key=lambda item: (item[0], item[1].award_value), reverse=True)
    values = sorted(item[1].award_value for item in similar)
    award_min = values[0]
    award_median = float(median(values))
    award_max = values[-1]
    accessibility = _accessibility_text(award_median, award_max, profile)

    evidence = [
        f"{len(similar)} similar awarded contracts found.",
        f"Historical award range: ${award_min:,.0f} - ${award_max:,.0f}.",
    ]
    for _, award, terms in similar[:3]:
        descriptor = award.description or award.category or award.document_number
        matched = ", ".join(terms[:5]) if terms else "category/type"
        evidence.append(f"{award.document_number or 'Award'} matched on {matched}: {descriptor[:90]}")

    return HistoricalComparison(
        similar_count=len(similar),
        award_min=award_min,
        award_median=award_median,
        award_max=award_max,
        accessibility=accessibility,
        evidence=evidence,
        examples=[_sample_award_dict(award, terms) for _, award, terms in similar[:3]],
    )


def meaningful_terms(text: str) -> set[str]:
    words = set()
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9&/-]{2,}", text.lower()):
        token = token.strip("-/").replace("&", "and")
        if token and token not in STOP_WORDS and len(token) > 2:
            words.add(token)
    return words


def _text_for(record: Solicitation | AwardRecord) -> str:
    return " ".join(
        [
            record.solicitation_type,
            record.category,
            record.division,
            record.description,
        ]
    )


def _similarity_score(
    solicitation: Solicitation,
    award: AwardRecord,
    solicitation_terms: set[str],
) -> tuple[int, list[str]]:
    score = 0
    evidence_terms: list[str] = []

    if _norm(solicitation.category) and _norm(solicitation.category) == _norm(award.category):
        score += 3
        evidence_terms.append("category")
    if _type_family(solicitation.solicitation_type) == _type_family(award.solicitation_type):
        score += 2
        evidence_terms.append("solicitation type")
    if _norm(solicitation.division) and _norm(solicitation.division) == _norm(award.division):
        score += 1
        evidence_terms.append("division")

    award_terms = meaningful_terms(_text_for(award))
    overlap = sorted(solicitation_terms & award_terms)
    service_terms = [
        term
        for term in overlap
        if term not in {"goods", "professional", "general", "construction", "repairs"}
    ]
    if not service_terms:
        return score, evidence_terms
    score += min(len(service_terms), 5)
    evidence_terms.extend(service_terms[:6])

    return score, evidence_terms


def _type_family(value: str) -> str:
    text = value.lower()
    if "rfq" in text or "quotation" in text:
        return "rfq"
    if "rfsq" in text or "supplier qualification" in text:
        return "rfsq"
    if "rfp" in text or "proposal" in text:
        return "rfp"
    if "tender" in text:
        return "tender"
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _accessibility_text(award_median: float, award_max: float, profile: BusinessProfile) -> str:
    if award_median <= 0:
        return "insufficient history"
    if award_median <= profile.max_contract_value and award_max <= profile.max_contract_value * 1.75:
        return "historically accessible for this business size"
    if award_median <= profile.max_contract_value * 1.5:
        return "possibly accessible, but may need a partner"
    return "historically larger than this business capacity"


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _profile_award_fit(profile: BusinessProfile, award: AwardRecord) -> tuple[int, list[str]]:
    text = _text_for(award)
    text_lower = text.lower()
    text_terms = meaningful_terms(text)
    profile_terms = meaningful_terms(" ".join([profile.business_type, *profile.skills]))
    missing_terms = meaningful_terms(" ".join(profile.missing_capabilities))

    if _contains_complex_scope(profile, text_lower) or len(missing_terms & text_terms) >= 2:
        return 0, []

    evidence_terms: list[str] = []
    score = 0

    business_terms = meaningful_terms(profile.business_type)
    business_overlap = sorted(business_terms & text_terms)
    if len(business_overlap) >= 2:
        score += 3
        evidence_terms.extend(business_overlap[:4])

    for skill in profile.skills:
        skill_text = skill.lower().strip()
        skill_terms = meaningful_terms(skill_text)
        if not skill_terms:
            continue
        if skill_text and skill_text in text_lower:
            score += 4
            evidence_terms.append(skill_text)
        else:
            overlap = sorted(skill_terms & text_terms)
            if len(overlap) >= 2:
                score += 3
                evidence_terms.append(skill_text)
            elif overlap:
                score += 1
                evidence_terms.extend(overlap)

    term_overlap = sorted(profile_terms & text_terms)
    score += min(len(term_overlap), 5)
    evidence_terms.extend(term_overlap[:8])

    if _type_family(award.solicitation_type) in {"rfq", "tender"}:
        score += 1

    if award.award_value > 0:
        if award.award_value <= profile.max_contract_value:
            score += 3
        elif award.award_value <= profile.max_contract_value * 1.25 and len(set(evidence_terms)) >= 4:
            score += 1
        else:
            return 0, []

    unique_evidence = _ordered_unique(evidence_terms)
    if score < 7 or len(unique_evidence) < 2:
        return 0, []

    return score, unique_evidence


def _contains_complex_scope(profile: BusinessProfile, text: str) -> bool:
    terms = set(COMPLEX_PAST_SCOPE_TERMS)
    if profile.profile_id == "professional_engineering_design":
        terms.discard("engineering services")
    elif profile.profile_id == "road_civil_infrastructure":
        terms -= {"bonding", "general contractor", "major construction", "prime contractor"}
    elif profile.profile_id == "parks_landscape":
        terms.discard("bonding")
    normalized = _norm(text)
    return any(term in text or term in normalized for term in terms)


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        clean = value.strip().lower()
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return unique


def _top_counts(values: Any) -> list[dict[str, Any]]:
    counter = Counter(value.strip() for value in values if isinstance(value, str) and value.strip())
    return [{"name": name, "count": count} for name, count in counter.most_common(5)]


def _top_terms(values: Any) -> list[str]:
    counter = Counter(value.strip().lower() for value in values if isinstance(value, str) and value.strip())
    return [term for term, _ in counter.most_common(10)]


def _buyer_name(award: AwardRecord) -> str:
    for field_name in AWARD_BUYER_FIELDS:
        value = award.raw.get(field_name)
        if value:
            return str(value)
    return ""


def _sample_award_dict(award: AwardRecord, matched_terms: list[str]) -> dict[str, Any]:
    return {
        "document_number": award.document_number,
        "description": award.description,
        "division": award.division,
        "buyer": _buyer_name(award),
        "supplier": award.supplier,
        "award_value": award.award_value,
        "award_date": award.award_date.isoformat() if award.award_date else None,
        "matched_terms": matched_terms[:6],
    }


def _award_value_range(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"available_count": 0}
    return {
        "min": values[0],
        "median": float(median(values)),
        "max": values[-1],
        "available_count": len(values),
    }


def _summary_evidence(
    realistic_count: int,
    values: list[float],
    divisions: list[dict[str, Any]],
    buyers: list[dict[str, Any]],
    evidence_terms: list[str],
) -> list[str]:
    if realistic_count == 0:
        return ["No realistic matching awarded contracts were found for this profile."]

    evidence = [f"{realistic_count} past awarded contracts look realistic for this profile."]
    if values:
        evidence.append(f"Matched award values range from ${values[0]:,.0f} to ${values[-1]:,.0f}.")
    if divisions:
        evidence.append(f"Most common division: {divisions[0]['name']}.")
    if buyers:
        evidence.append(f"Most common buyer: {buyers[0]['name']}.")
    if evidence_terms:
        evidence.append(f"Recurring evidence terms: {', '.join(evidence_terms[:6])}.")
    return evidence
