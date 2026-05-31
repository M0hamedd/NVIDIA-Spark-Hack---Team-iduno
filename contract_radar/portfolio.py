from __future__ import annotations

from importlib import util
from typing import Any

from contract_radar.models import BusinessProfile, EvaluatedOpportunity, PortfolioDecision


def cuopt_status() -> dict[str, Any]:
    installed = util.find_spec("cuopt") is not None
    return {
        "available": False,
        "installed": installed,
        "mode": "greedy_fallback",
        "cuopt_hook_ready": installed,
        "purpose": "Portfolio-level bid selection under estimator hours, pursuit load, deadline, and capacity constraints.",
        "note": "cuOpt package detection is wired, but this build uses the deterministic optimizer until a cuOpt solver adapter is configured.",
    }


def optimize_bid_portfolio(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
    priority_mode: str = "best_win_chance",
) -> list[EvaluatedOpportunity]:
    status = cuopt_status()
    engine = str(status["mode"])
    remaining_slots = max(0, int(profile.max_active_pursuits) - int(profile.active_pursuit_count))
    remaining_hours = _weekly_estimator_hours(profile)
    candidates = []

    for opportunity in opportunities:
        expected = _expected_value(opportunity, priority_mode)
        hours = _estimator_hours(opportunity)
        candidates.append((expected / max(hours, 1.0), expected, hours, opportunity))

    candidates.sort(key=lambda row: (row[0], row[1], -row[2]), reverse=True)
    selected_ids: set[str] = set()
    for _, expected, hours, opportunity in candidates:
        if opportunity.label == "Skip":
            continue
        if remaining_slots <= 0 or remaining_hours < hours:
            continue
        if _must_review(opportunity):
            continue
        selected_ids.add(opportunity.solicitation.document_number)
        remaining_slots -= 1
        remaining_hours -= hours

    rank = 1
    for _, expected, hours, opportunity in sorted(candidates, key=lambda row: row[1], reverse=True):
        decision = _decision_for(opportunity, selected_ids, remaining_slots, remaining_hours)
        opportunity.portfolio_decision = PortfolioDecision(
            source="portfolio_optimizer",
            engine=engine,
            decision=decision,
            priority_rank=rank,
            expected_value=round(expected, 2),
            estimator_hours=round(hours, 1),
            capacity_used=opportunity.solicitation.document_number in selected_ids,
            reasons=_decision_reasons(opportunity, decision, hours, expected),
        )
        _attach_portfolio_to_trace(opportunity)
        rank += 1

    return sorted(
        opportunities,
        key=lambda item: (
            _decision_order(item.label),
            _portfolio_decision_order(item.portfolio_decision.decision),
            item.portfolio_decision.priority_rank or 9999,
            -item.revenue_score,
            item.days_until_deadline if item.days_until_deadline is not None else 9999,
            item.solicitation.document_number,
        ),
    )


def _decision_for(
    opportunity: EvaluatedOpportunity,
    selected_ids: set[str],
    remaining_slots: int,
    remaining_hours: float,
) -> str:
    if opportunity.label == "Skip":
        return "Pass"
    if opportunity.solicitation.document_number in selected_ids:
        return "Pursue Now"
    if _must_review(opportunity):
        return "Review"
    if opportunity.label == "Pursue" and (remaining_slots <= 0 or remaining_hours < _estimator_hours(opportunity)):
        return "Pursue If Capacity Frees"
    if opportunity.label == "Review":
        return "Review"
    return "Monitor"


def _expected_value(opportunity: EvaluatedOpportunity, priority_mode: str) -> float:
    fit_probability = max(0.02, min(0.98, float(opportunity.fit_probability or opportunity.market_fit.score or 0.1)))
    predicted = float(opportunity.predicted_bid or opportunity.bid_recommendation.recommended_bid or 0.0)
    simulated = float(opportunity.simulation_summary.likely_high or predicted)
    base = (predicted * 0.7 + simulated * 0.3) * fit_probability
    risk_discount = max(0.25, 1.0 - (float(opportunity.risk_score or 0.0) / 180.0))
    if priority_mode == "highest_value":
        return base * risk_discount
    if priority_mode == "best_fit":
        return base * risk_discount * (1.0 + min(0.5, opportunity.rank_score / 200.0))
    return base * risk_discount * (1.0 + min(0.35, opportunity.rank_score / 250.0))


def _estimator_hours(opportunity: EvaluatedOpportunity) -> float:
    hours = 6.0
    if opportunity.bid_recommendation.recommended_bid > 1000000:
        hours += 4.0
    if opportunity.capacity_assessment.execution_capacity != "Fits Team":
        hours += 3.0
    if opportunity.days_until_deadline is not None and opportunity.days_until_deadline < 5:
        hours += 2.0
    if opportunity.requirements.documents or opportunity.opportunity_brief.required_documents:
        hours += min(4.0, len(opportunity.requirements.documents) + len(opportunity.opportunity_brief.required_documents))
    return hours


def _weekly_estimator_hours(profile: BusinessProfile) -> float:
    return max(8.0, min(56.0, float(profile.team_size) * 1.25))


def _must_review(opportunity: EvaluatedOpportunity) -> bool:
    return bool(
        opportunity.label == "Review"
        or opportunity.capacity_assessment.recommended_action == "Pursue After Review"
        or opportunity.capacity_assessment.execution_capacity == "Likely Too Large"
        or opportunity.risk_score >= 55
    )


def _decision_reasons(opportunity: EvaluatedOpportunity, decision: str, hours: float, expected: float) -> list[str]:
    reasons = [f"Expected revenue-weighted value ${expected:,.0f}; estimated pursuit effort {hours:.1f} hours."]
    if decision == "Pursue Now":
        reasons.append("Selected inside pursuit capacity and risk constraints.")
    elif decision == "Pursue If Capacity Frees":
        reasons.append("Strong candidate, but current pursuit capacity is reserved for higher-value work.")
    elif decision == "Review":
        reasons.append("Human review required before using pursuit capacity.")
    elif decision == "Pass":
        reasons.append("Excluded by deterministic bid gates.")
    else:
        reasons.append("Keep watching; not selected for immediate pursuit.")
    return reasons


def _attach_portfolio_to_trace(opportunity: EvaluatedOpportunity) -> None:
    decision = opportunity.portfolio_decision
    if not decision.decision:
        return
    message = f"Portfolio optimizer: {decision.decision} (rank {decision.priority_rank})."
    if message not in opportunity.bid_fitness_trace.capacity_gates:
        opportunity.bid_fitness_trace.capacity_gates.append(message)
    opportunity.bid_fitness_trace.scorecard_labels["Portfolio Decision"] = decision.decision


def _decision_order(label: str) -> int:
    return {
        "Pursue": 0,
        "Review": 1,
        "Monitor": 2,
        "Skip": 3,
    }.get(label, 2)


def _portfolio_decision_order(decision: str) -> int:
    return {
        "Pursue Now": 0,
        "Pursue If Capacity Frees": 1,
        "Review": 2,
        "Monitor": 3,
        "Pass": 4,
    }.get(decision, 3)
