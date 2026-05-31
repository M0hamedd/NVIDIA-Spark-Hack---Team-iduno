from __future__ import annotations

import math

from contract_radar.models import BusinessProfile, EvaluatedOpportunity, PricingBreakdown


def attach_bid_pricing(
    profile: BusinessProfile,
    opportunities: list[EvaluatedOpportunity],
) -> list[EvaluatedOpportunity]:
    for opportunity in opportunities:
        opportunity.pricing_breakdown = price_opportunity(profile, opportunity)
        if opportunity.pricing_breakdown.recommended_bid > 0:
            opportunity.predicted_bid = opportunity.pricing_breakdown.recommended_bid
            _attach_pricing_to_trace(opportunity)
    return opportunities


def price_opportunity(profile: BusinessProfile, opportunity: EvaluatedOpportunity) -> PricingBreakdown:
    market_reference = _market_reference(opportunity)
    if market_reference <= 0 or opportunity.label == "Skip":
        return PricingBreakdown(
            source="insufficient_market_value" if opportunity.label != "Skip" else "skipped_by_bid_gates",
            evidence=["Pricing engine needs a non-skipped listing with historical market value evidence."],
        )

    complexity_score, drivers = _complexity_score(opportunity)
    direct_cost_rate = _direct_cost_rate(profile, opportunity)
    contingency_rate = _contingency_rate(opportunity, complexity_score)
    overhead_rate = _overhead_rate(profile, opportunity)
    margin_rate = _margin_rate(profile, opportunity)
    bid_prep_cost = _bid_prep_cost(opportunity)

    direct_cost = market_reference * direct_cost_rate
    contingency = direct_cost * contingency_rate
    overhead = direct_cost * overhead_rate
    estimated_cost = direct_cost + contingency + overhead
    cost_based_bid = estimated_cost / max(0.55, 1.0 - margin_rate)
    market_adjusted_bid = cost_based_bid * 0.60 + market_reference * 0.40

    candidates = _candidate_bids(
        center=market_adjusted_bid,
        estimated_cost=estimated_cost,
        market_reference=market_reference,
        bid_prep_cost=bid_prep_cost,
        opportunity=opportunity,
    )
    best = max(candidates, key=lambda item: item["expected_profit"])
    recommended = _round_money(float(best["bid"]))
    risk_multiplier = max(0.55, min(1.55, 1.0 + complexity_score * 0.42 + _deadline_risk(opportunity) * 0.18))

    evidence = [
        (
            f"Pricing engine starts from ${market_reference:,.0f} historical market value, "
            f"then estimates direct cost, contingency, overhead, and margin."
        ),
        (
            f"Cost stack: direct ${direct_cost:,.0f}, contingency ${contingency:,.0f}, "
            f"overhead ${overhead:,.0f}, target margin {margin_rate:.0%}."
        ),
        (
            f"Optimizer tested {len(candidates)} bid prices and selected ${recommended:,.0f} "
            f"at {float(best['win_probability']):.0%} estimated win probability."
        ),
    ]

    return PricingBreakdown(
        source="scope_cost_market_optimizer",
        market_reference=_round_money(market_reference),
        direct_cost=_round_money(direct_cost),
        contingency=_round_money(contingency),
        overhead=_round_money(overhead),
        margin=_round_money(recommended - estimated_cost),
        estimated_cost=_round_money(estimated_cost),
        cost_based_bid=_round_money(cost_based_bid),
        market_adjusted_bid=_round_money(market_adjusted_bid),
        recommended_bid=recommended,
        win_probability=round(float(best["win_probability"]), 4),
        expected_profit=_round_money(float(best["expected_profit"])),
        bid_prep_cost=_round_money(bid_prep_cost),
        complexity_score=round(complexity_score, 4),
        risk_multiplier=round(risk_multiplier, 4),
        overhead_rate=round(overhead_rate, 4),
        margin_rate=round(margin_rate, 4),
        contingency_rate=round(contingency_rate, 4),
        market_weight=0.40,
        cost_weight=0.60,
        candidate_bids=candidates,
        drivers=drivers,
        evidence=evidence,
    )


def _market_reference(opportunity: EvaluatedOpportunity) -> float:
    values = [
        opportunity.bid_recommendation.recommended_bid,
        opportunity.rag_evidence.value_median,
        opportunity.historical.award_median,
        opportunity.bid_recommendation.median_award,
        opportunity.historical.award_max,
    ]
    clean = [float(value) for value in values if float(value or 0.0) > 0]
    if not clean:
        return 0.0
    if len(clean) == 1:
        return clean[0]
    primary = clean[0]
    analogs = clean[1:]
    return primary * 0.65 + (sum(analogs) / len(analogs)) * 0.35


def _complexity_score(opportunity: EvaluatedOpportunity) -> tuple[float, list[str]]:
    text = " ".join(
        [
            opportunity.solicitation.description,
            opportunity.solicitation.category,
            opportunity.solicitation.division,
            " ".join(opportunity.matched_terms),
            " ".join(opportunity.requirements.risk_flags),
            " ".join(opportunity.requirements.capacity_flags),
        ]
    ).lower()
    signals = {
        "traffic staging": 0.10,
        "traffic control": 0.08,
        "bridge": 0.16,
        "watermain": 0.14,
        "sewer": 0.13,
        "multi-site": 0.09,
        "multiple": 0.05,
        "contract administration": 0.08,
        "inspection": 0.07,
        "detailed design": 0.08,
        "emergency": 0.12,
        "rehabilitation": 0.08,
        "construction": 0.08,
        "playground": 0.07,
        "arborist": 0.06,
    }
    drivers: list[str] = []
    score = 0.10
    for signal, weight in signals.items():
        if signal in text:
            score += weight
            drivers.append(signal)
    if opportunity.days_until_deadline is not None and opportunity.days_until_deadline < 7:
        score += 0.10
        drivers.append("tight deadline")
    if opportunity.capacity_assessment.execution_capacity != "Fits Team":
        score += 0.08
        drivers.append("capacity pressure")
    return min(0.85, score), drivers[:6] or ["ordinary scope complexity"]


def _direct_cost_rate(profile: BusinessProfile, opportunity: EvaluatedOpportunity) -> float:
    profile_text = f"{profile.profile_id} {profile.business_type}".lower()
    category = opportunity.solicitation.category.lower()
    if "engineering" in profile_text or "professional services" in category:
        return 0.58
    if "parks" in profile_text or "landscape" in profile_text:
        return 0.66
    if "construction" in category or "civil" in profile_text:
        return 0.72
    return 0.68


def _contingency_rate(opportunity: EvaluatedOpportunity, complexity_score: float) -> float:
    rate = 0.07 + complexity_score * 0.20
    if opportunity.bid_recommendation.confidence.lower() in {"low", "unknown"}:
        rate += 0.04
    if len(opportunity.rag_evidence.analogs) < 3:
        rate += 0.03
    return min(0.28, max(0.07, rate))


def _overhead_rate(profile: BusinessProfile, opportunity: EvaluatedOpportunity) -> float:
    profile_text = f"{profile.profile_id} {profile.business_type}".lower()
    if "engineering" in profile_text or "professional services" in opportunity.solicitation.category.lower():
        return 0.18
    if "parks" in profile_text or "landscape" in profile_text:
        return 0.13
    return 0.11


def _margin_rate(profile: BusinessProfile, opportunity: EvaluatedOpportunity) -> float:
    base = 0.12
    if "engineering" in f"{profile.profile_id} {profile.business_type}".lower():
        base = 0.18
    elif "parks" in profile.profile_id:
        base = 0.14
    if opportunity.market_fit.supplier_concentration:
        top_share = float(opportunity.market_fit.supplier_concentration.get("top_supplier_share") or 0.0)
        base -= min(0.04, top_share * 0.04)
    return min(0.22, max(0.08, base))


def _bid_prep_cost(opportunity: EvaluatedOpportunity) -> float:
    effort = 1800.0
    if opportunity.solicitation.solicitation_type.lower().find("proposal") >= 0:
        effort += 4200.0
    if opportunity.days_until_deadline is not None and opportunity.days_until_deadline < 7:
        effort += 1200.0
    if opportunity.label == "Review":
        effort += 900.0
    return effort


def _candidate_bids(
    center: float,
    estimated_cost: float,
    market_reference: float,
    bid_prep_cost: float,
    opportunity: EvaluatedOpportunity,
) -> list[dict[str, float]]:
    candidates = []
    for multiplier in (0.88, 0.94, 1.0, 1.06, 1.12):
        bid = _round_money(center * multiplier)
        win_probability = _win_probability(bid, market_reference, opportunity)
        expected_profit = win_probability * max(0.0, bid - estimated_cost) - bid_prep_cost
        candidates.append(
            {
                "bid": bid,
                "win_probability": round(win_probability, 4),
                "expected_profit": _round_money(expected_profit),
            }
        )
    return candidates


def _win_probability(bid: float, market_reference: float, opportunity: EvaluatedOpportunity) -> float:
    if market_reference <= 0:
        return 0.0
    fit = max(0.08, min(0.95, float(opportunity.fit_probability or opportunity.market_fit.score or 0.35)))
    price_ratio = bid / market_reference
    price_effect = 1.0 / (1.0 + math.exp((price_ratio - 1.0) * 7.0))
    competition = float((opportunity.market_fit.supplier_concentration or {}).get("top_supplier_share") or 0.0)
    competition_penalty = min(0.22, competition * 0.18)
    deadline_penalty = _deadline_risk(opportunity) * 0.08
    return max(0.04, min(0.92, fit * 0.45 + price_effect * 0.45 + 0.10 - competition_penalty - deadline_penalty))


def _deadline_risk(opportunity: EvaluatedOpportunity) -> float:
    days = opportunity.days_until_deadline
    if days is None:
        return 0.20
    if days < 3:
        return 0.80
    if days < 7:
        return 0.45
    if days < 14:
        return 0.20
    return 0.05


def _round_money(value: float) -> float:
    amount = max(0.0, float(value or 0.0))
    if amount <= 0:
        return 0.0
    if amount < 100000:
        increment = 1000
    elif amount < 1000000:
        increment = 5000
    else:
        increment = 10000
    return float(round(amount / increment) * increment)


def _attach_pricing_to_trace(opportunity: EvaluatedOpportunity) -> None:
    pricing = opportunity.pricing_breakdown
    message = (
        f"Pricing engine: cost stack ${pricing.estimated_cost:,.0f}, optimized bid "
        f"${pricing.recommended_bid:,.0f}, expected profit ${pricing.expected_profit:,.0f}."
    )
    if message not in opportunity.bid_fitness_trace.positive_signals:
        opportunity.bid_fitness_trace.positive_signals.append(message)
    opportunity.bid_fitness_trace.scorecard_labels["Pricing Engine"] = f"{pricing.win_probability:.0%} win"
