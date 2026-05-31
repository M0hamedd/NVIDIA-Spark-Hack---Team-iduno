from __future__ import annotations

import hashlib
import random
from statistics import median

from contract_radar.models import BusinessProfile, EvaluatedOpportunity, SimulationSummary


ITERATIONS = 512


def attach_revenue_simulations(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
) -> list[EvaluatedOpportunity]:
    for opportunity in opportunities:
        opportunity.simulation_summary = simulate_revenue(profile, opportunity)
        _attach_simulation_to_trace(opportunity)
    return opportunities


def simulate_revenue(profile: BusinessProfile, opportunity: EvaluatedOpportunity, iterations: int = ITERATIONS) -> SimulationSummary:
    predicted = float(opportunity.predicted_bid or opportunity.bid_recommendation.recommended_bid or 0.0)
    if predicted <= 0:
        return SimulationSummary(
            source="deterministic_monte_carlo",
            seed=_seed(opportunity),
            iterations=0,
            drivers=["No predicted bid was available for revenue simulation."],
        )

    seed = _seed(opportunity)
    rng = random.Random(seed)
    rag = opportunity.rag_evidence
    fit_probability = max(0.05, min(0.98, float(opportunity.fit_probability or opportunity.market_fit.score or 0.35)))
    uncertainty = _uncertainty(opportunity)
    supplier_concentration = float((opportunity.market_fit.supplier_concentration or {}).get("top_supplier_share") or 0.0)
    deadline_penalty = _deadline_penalty(opportunity.days_until_deadline)
    capacity_penalty = _capacity_penalty(opportunity)
    competition_penalty = min(0.22, supplier_concentration * 0.16)
    risk_multiplier = max(0.45, 1.0 - deadline_penalty - capacity_penalty - competition_penalty)

    samples = []
    center = predicted * risk_multiplier
    for _ in range(max(32, iterations)):
        noise = rng.normalvariate(0.0, uncertainty)
        scenario = max(0.0, center * (1.0 + noise))
        samples.append(scenario)
    samples.sort()

    downside = _percentile(samples, 0.10)
    low = _percentile(samples, 0.25)
    high = _percentile(samples, 0.75)
    upside = _percentile(samples, 0.90)
    drivers = _drivers(opportunity, uncertainty, deadline_penalty, capacity_penalty, competition_penalty, rag.value_median)
    confidence = _confidence(uncertainty, len(rag.analogs), fit_probability)
    opportunity.revenue_score = round((median(samples) / max(profile.max_contract_value, 1.0)) * fit_probability * 100, 2)
    opportunity.risk_score = round((1.0 - risk_multiplier + uncertainty) * 100, 2)

    return SimulationSummary(
        source="deterministic_monte_carlo",
        seed=seed,
        iterations=max(32, iterations),
        downside_case=_round_money(downside),
        likely_low=_round_money(low),
        likely_high=_round_money(high),
        upside_case=_round_money(upside),
        confidence=confidence,
        drivers=drivers,
    )


def _attach_simulation_to_trace(opportunity: EvaluatedOpportunity) -> None:
    summary = opportunity.simulation_summary
    if not summary.iterations:
        return
    message = (
        f"Simulation: likely revenue range ${summary.likely_low:,.0f} - "
        f"${summary.likely_high:,.0f} ({summary.confidence.lower()} confidence)."
    )
    if message not in opportunity.bid_fitness_trace.positive_signals:
        opportunity.bid_fitness_trace.positive_signals.append(message)
    opportunity.bid_fitness_trace.scorecard_labels["Revenue Simulation"] = summary.confidence


def _uncertainty(opportunity: EvaluatedOpportunity) -> float:
    analog_count = len(opportunity.rag_evidence.analogs)
    confidence = str(opportunity.bid_recommendation.confidence or "").lower()
    base = 0.34
    if analog_count >= 8:
        base -= 0.08
    elif analog_count >= 4:
        base -= 0.04
    if confidence in {"strong", "moderate"}:
        base -= 0.04
    if opportunity.days_until_deadline is not None and opportunity.days_until_deadline < 5:
        base += 0.05
    if opportunity.capacity_assessment.execution_capacity != "Fits Team":
        base += 0.05
    return max(0.14, min(0.48, base))


def _drivers(
    opportunity: EvaluatedOpportunity,
    uncertainty: float,
    deadline_penalty: float,
    capacity_penalty: float,
    competition_penalty: float,
    rag_median: float,
) -> list[str]:
    drivers = []
    if rag_median:
        drivers.append(f"RAG analog median award is ${rag_median:,.0f}.")
    if deadline_penalty:
        drivers.append("Downside moved lower because the submission deadline is tight.")
    if capacity_penalty:
        drivers.append("Capacity review widened the uncertainty band.")
    if competition_penalty:
        drivers.append("Supplier concentration adds competition risk.")
    drivers.append(f"Model uncertainty band uses {uncertainty:.0%} deterministic scenario noise.")
    return drivers


def _deadline_penalty(days: int | None) -> float:
    if days is None:
        return 0.08
    if days < 0:
        return 0.30
    if days < 5:
        return 0.12
    if days <= 10:
        return 0.06
    return 0.0


def _capacity_penalty(opportunity: EvaluatedOpportunity) -> float:
    assessment = opportunity.capacity_assessment
    penalty = 0.0
    if assessment.pursuit_load == "Overloaded":
        penalty += 0.12
    elif assessment.pursuit_load == "Busy":
        penalty += 0.06
    if assessment.execution_capacity == "Likely Too Large":
        penalty += 0.18
    elif assessment.execution_capacity == "Needs Scheduling Review":
        penalty += 0.08
    return min(0.26, penalty)


def _confidence(uncertainty: float, analog_count: int, fit_probability: float) -> str:
    if uncertainty <= 0.2 and analog_count >= 6 and fit_probability >= 0.65:
        return "Strong"
    if uncertainty <= 0.3 and analog_count >= 4:
        return "Moderate"
    return "Directional"


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * max(0.0, min(1.0, quantile))
    lower = int(position)
    upper = min(len(values) - 1, lower + 1)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[upper] * fraction


def _round_money(value: float) -> float:
    if value < 100000:
        increment = 1000
    elif value < 1000000:
        increment = 5000
    else:
        increment = 10000
    return float(round(max(0.0, value) / increment) * increment)


def _seed(opportunity: EvaluatedOpportunity) -> int:
    key = f"{opportunity.solicitation.document_number}:{opportunity.predicted_bid}:{opportunity.rank_score}"
    return int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:12], 16)
