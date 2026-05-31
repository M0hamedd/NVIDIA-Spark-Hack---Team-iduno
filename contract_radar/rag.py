from __future__ import annotations

import math
from statistics import median
from typing import Any

from contract_radar.history import meaningful_terms
from contract_radar.models import AwardRecord, BusinessProfile, EvaluatedOpportunity, RAGEvidence, Solicitation


DEFAULT_TOP_K = 8


def attach_rag_evidence(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
    awards: list[AwardRecord],
    top_k: int = DEFAULT_TOP_K,
) -> list[EvaluatedOpportunity]:
    retriever = AwardRetriever(profile, awards)
    for opportunity in opportunities:
        opportunity.rag_evidence = retriever.retrieve(opportunity.solicitation, top_k=top_k)
        _attach_rag_to_trace(opportunity)
    return opportunities


class AwardRetriever:
    def __init__(self, profile: BusinessProfile, awards: list[AwardRecord]) -> None:
        self.profile = profile
        self.awards = [
            award
            for award in awards
            if award.award_value > 0 and _profile_relevant(profile, award)
        ]
        self.mode = "lexical_tfidf_fallback"
        self._tfidf: Any | None = None
        self._matrix: Any | None = None
        self._texts = [_award_text(award) for award in self.awards]
        self._configure_vectorizer()

    def retrieve(self, solicitation: Solicitation, top_k: int = DEFAULT_TOP_K) -> RAGEvidence:
        if not self.awards:
            return RAGEvidence(
                source="historical_award_rag",
                mode=self.mode,
                evidence=["No profile-relevant historical awards were available for retrieval."],
            )

        query = _solicitation_text(solicitation)
        initial = self._lexical_candidates(query, limit=max(top_k * 6, 30))
        ranked = sorted(
            (
                (
                    _rerank_score(query, solicitation, award, score),
                    score,
                    award,
                )
                for award, score in initial
            ),
            key=lambda row: (float(row[0]), float(row[1]), row[2].document_number),
            reverse=True,
        )
        top = ranked[:top_k]
        values = sorted(award.award_value for _, _, award in top if award.award_value > 0)
        similarities = [float(score) for _, score, _ in top]
        analogs = [
            _analog_dict(solicitation, award, similarity=sim_score, rerank_score=rank_score)
            for rank_score, sim_score, award in top
        ]
        same_buyer_count = sum(
            1 for _, _, award in top if _norm(_buyer_name(award)) and _norm(_buyer_name(award)) == _norm(solicitation.buyer_name)
        )
        same_division_count = sum(1 for _, _, award in top if _norm(award.division) == _norm(solicitation.division))
        same_type_count = sum(1 for _, _, award in top if _type_family(award.solicitation_type) == _type_family(solicitation.solicitation_type))
        evidence = [
            (
                f"Retrieved {len(top)} historical award analog(s) with {self.mode}; "
                f"top similarity {similarities[0]:.2f}."
            )
            if similarities
            else f"Retrieved {len(top)} historical award analog(s) with {self.mode}.",
        ]
        if values:
            evidence.append(f"RAG analog value range: ${values[0]:,.0f} - ${values[-1]:,.0f}.")
        if same_division_count or same_type_count:
            evidence.append(
                f"{same_division_count} same-division and {same_type_count} same-contract-type analog(s) found."
            )

        return RAGEvidence(
            source="historical_award_rag",
            mode=self.mode,
            top_similarity=round(similarities[0], 4) if similarities else 0.0,
            average_similarity=round(sum(similarities) / len(similarities), 4) if similarities else 0.0,
            same_buyer_count=same_buyer_count,
            same_division_count=same_division_count,
            same_type_count=same_type_count,
            value_min=values[0] if values else 0.0,
            value_median=float(median(values)) if values else 0.0,
            value_max=values[-1] if values else 0.0,
            evidence=evidence,
            analogs=analogs,
        )

    def _configure_vectorizer(self) -> None:
        if not self._texts:
            return
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            self._tfidf = TfidfVectorizer(ngram_range=(1, 2), min_df=1, max_features=3000)
            self._matrix = self._tfidf.fit_transform(self._texts)
            self.mode = _retriever_mode()
        except Exception:
            self._tfidf = None
            self._matrix = None
            self.mode = "lexical_overlap_fallback"

    def _lexical_candidates(self, query: str, limit: int) -> list[tuple[AwardRecord, float]]:
        if self._tfidf is not None and self._matrix is not None:
            vector = self._tfidf.transform([query])
            scores = (self._matrix @ vector.T).toarray().ravel()
            rows = sorted(enumerate(scores), key=lambda row: float(row[1]), reverse=True)[:limit]
            return [(self.awards[index], float(score)) for index, score in rows if float(score) > 0]

        query_terms = meaningful_terms(query)
        rows = []
        for award in self.awards:
            award_terms = meaningful_terms(_award_text(award))
            score = _safe_ratio(len(query_terms & award_terms), math.sqrt(max(1, len(query_terms) * len(award_terms))))
            if score > 0:
                rows.append((award, score))
        return sorted(rows, key=lambda row: row[1], reverse=True)[:limit]


def rag_feature_values(evidence: RAGEvidence) -> dict[str, float]:
    values = [float(item.get("award_value") or 0.0) for item in evidence.analogs if isinstance(item, dict)]
    values = [value for value in values if value > 0]
    spread = (max(values) - min(values)) if values else 0.0
    return {
        "rag_top_similarity": float(evidence.top_similarity or 0.0),
        "rag_average_similarity": float(evidence.average_similarity or 0.0),
        "rag_top_value_log": math.log1p(values[0]) if values else 0.0,
        "rag_median_value_log": math.log1p(evidence.value_median) if evidence.value_median else 0.0,
        "rag_value_spread_log": math.log1p(spread),
        "rag_same_buyer_count": float(evidence.same_buyer_count),
        "rag_same_division_count": float(evidence.same_division_count),
        "rag_same_type_count": float(evidence.same_type_count),
        "rag_analog_count": float(len(evidence.analogs)),
    }


def _attach_rag_to_trace(opportunity: EvaluatedOpportunity) -> None:
    evidence = opportunity.rag_evidence
    if evidence.evidence:
        for message in evidence.evidence[:3]:
            if message not in opportunity.bid_fitness_trace.historical_analogs:
                opportunity.bid_fitness_trace.historical_analogs.append(message)
    if evidence.top_similarity:
        opportunity.bid_fitness_trace.scorecard_labels["RAG Evidence"] = f"{round(evidence.top_similarity * 100)}% top analog"


def _rerank_score(query: str, solicitation: Solicitation, award: AwardRecord, lexical_score: float) -> float:
    query_terms = meaningful_terms(query)
    award_terms = meaningful_terms(_award_text(award))
    service_overlap = len(query_terms & award_terms)
    same_division = 1.0 if _norm(solicitation.division) == _norm(award.division) else 0.0
    same_type = 1.0 if _type_family(solicitation.solicitation_type) == _type_family(award.solicitation_type) else 0.0
    same_category = 1.0 if _category_family(solicitation.category) == _category_family(award.category) else 0.0
    return float(lexical_score) * 8.0 + service_overlap * 0.35 + same_type * 1.2 + same_category * 0.8 + same_division * 0.8


def _analog_dict(solicitation: Solicitation, award: AwardRecord, similarity: float, rerank_score: float) -> dict[str, Any]:
    solicitation_terms = meaningful_terms(_solicitation_text(solicitation))
    award_terms = meaningful_terms(_award_text(award))
    matched_terms = sorted(solicitation_terms & award_terms)[:8]
    return {
        "document_number": award.document_number,
        "description": award.description,
        "division": award.division,
        "buyer": _buyer_name(award),
        "supplier": award.supplier,
        "award_value": award.award_value,
        "award_date": award.award_date.isoformat() if award.award_date else None,
        "solicitation_type": award.solicitation_type,
        "category": award.category,
        "similarity": round(float(similarity), 4),
        "rerank_score": round(float(rerank_score), 4),
        "same_buyer": bool(_norm(_buyer_name(award)) and _norm(_buyer_name(award)) == _norm(solicitation.buyer_name)),
        "same_division": _norm(award.division) == _norm(solicitation.division),
        "same_type": _type_family(award.solicitation_type) == _type_family(solicitation.solicitation_type),
        "matched_terms": matched_terms,
        "why_it_matters": _why_it_matters(solicitation, award, matched_terms),
    }


def _profile_relevant(profile: BusinessProfile, award: AwardRecord) -> bool:
    score, _ = _profile_award_fit_safe(profile, award)
    return score > 0


def _profile_award_fit_safe(profile: BusinessProfile, award: AwardRecord) -> tuple[int, list[str]]:
    from contract_radar.history import _profile_award_fit

    return _profile_award_fit(profile, award)


def _why_it_matters(solicitation: Solicitation, award: AwardRecord, matched_terms: list[str]) -> str:
    reasons = []
    if _type_family(award.solicitation_type) == _type_family(solicitation.solicitation_type):
        reasons.append("same contract type")
    if _norm(award.division) == _norm(solicitation.division):
        reasons.append("same division")
    if matched_terms:
        reasons.append(f"shared scope terms: {', '.join(matched_terms[:4])}")
    if award.award_value:
        reasons.append(f"historical value ${award.award_value:,.0f}")
    return "; ".join(reasons) or "retrieved as a historical analog"


def _retriever_mode() -> str:
    return "tfidf_hybrid_fallback"


def _solicitation_text(solicitation: Solicitation) -> str:
    return " ".join([solicitation.solicitation_type, solicitation.category, solicitation.division, solicitation.description])


def _award_text(award: AwardRecord) -> str:
    return " ".join([award.solicitation_type, award.category, award.division, award.description, award.supplier])


def _buyer_name(award: AwardRecord) -> str:
    for field_name in ("Buyer Name", "buyer_name", "Buyer", "buyer", "Buyer Contact", "buyer_contact"):
        value = award.raw.get(field_name)
        if value:
            return str(value)
    return ""


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
    return _norm(text)


def _category_family(value: str) -> str:
    text = value.lower()
    if "construction" in text:
        return "construction"
    if "professional" in text or "consulting" in text:
        return "professional"
    if "goods" in text or "supplies" in text or "supply" in text:
        return "goods"
    return _norm(text) or "unknown"


def _norm(value: str) -> str:
    return " ".join(str(value or "").lower().split())


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)
