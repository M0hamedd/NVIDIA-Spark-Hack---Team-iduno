from __future__ import annotations

import unittest
from datetime import date

from contract_radar.matcher import evaluate_opportunities
from contract_radar.models import AwardRecord, Solicitation
from contract_radar.portfolio import optimize_bid_portfolio
from contract_radar.profiles import get_supported_profile
from contract_radar.rag import AwardRetriever, attach_rag_evidence
from contract_radar.ranker import apply_market_intelligence, train_award_history_market_model
from contract_radar.revenue_simulation import simulate_revenue


TODAY = date(2026, 5, 30)


class RobustPipelineTests(unittest.TestCase):
    def test_rag_retrieves_scope_relevant_awards(self) -> None:
        profile = get_supported_profile("road_civil_infrastructure")
        awards = [
            _award("ROAD-1", "Road repairs, asphalt paving, curb repair, and traffic staging.", 500000),
            _award("PARK-1", "Playground installation, planting, trail repairs, and site furnishings.", 250000, division="Parks, Forestry & Recreation"),
        ]
        retriever = AwardRetriever(profile, awards)

        evidence = retriever.retrieve(
            _solicitation("SOL-ROAD", "Road repairs, asphalt paving, curb repair, and traffic staging."),
            top_k=3,
        )

        self.assertEqual(evidence.source, "historical_award_rag")
        self.assertGreater(evidence.top_similarity, 0)
        self.assertEqual(evidence.analogs[0]["document_number"], "ROAD-1")
        self.assertIn("same contract type", evidence.analogs[0]["why_it_matters"])

    def test_simulation_is_repeatable_for_same_opportunity(self) -> None:
        profile, opportunity = _scored_opportunity()

        first = simulate_revenue(profile, opportunity)
        second = simulate_revenue(profile, opportunity)

        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertGreater(first.likely_high, first.likely_low)
        self.assertTrue(first.drivers)

    def test_optimizer_respects_active_pursuit_capacity(self) -> None:
        profile, opportunity = _scored_opportunity()
        profile.active_pursuit_count = profile.max_active_pursuits

        optimized = optimize_bid_portfolio(profile, [opportunity])

        decision = optimized[0].portfolio_decision
        self.assertIn(decision.decision, {"Pursue If Capacity Frees", "Review", "Monitor"})
        self.assertFalse(decision.capacity_used)
        self.assertGreater(decision.expected_value, 0)


def _scored_opportunity() -> tuple[object, object]:
    profile = get_supported_profile("road_civil_infrastructure")
    awards = [
        _award("ROAD-1", "Road repairs, asphalt paving, curb repair, and traffic staging.", 500000, award_date=date(2022, 1, 1)),
        _award("ROAD-2", "Road repairs, asphalt paving, curb repair, and traffic staging.", 650000, award_date=date(2023, 1, 1)),
        _award("ROAD-3", "Road repairs, asphalt paving, curb repair, and traffic staging.", 725000, award_date=date(2024, 1, 1)),
        _award("ROAD-4", "Road repairs, asphalt paving, curb repair, and traffic staging.", 800000, award_date=date(2025, 1, 1)),
        _award("ROAD-5", "Road repairs, asphalt paving, curb repair, and traffic staging.", 850000, award_date=date(2025, 2, 1)),
        _award("ROAD-6", "Road repairs, asphalt paving, curb repair, and traffic staging.", 900000, award_date=date(2025, 3, 1)),
        _award("ROAD-7", "Road repairs, asphalt paving, curb repair, and traffic staging.", 950000, award_date=date(2025, 4, 1)),
        _award("ROAD-8", "Road repairs, asphalt paving, curb repair, and traffic staging.", 990000, award_date=date(2025, 5, 1)),
        _award("SW-0", "Software licensing and data migration.", 180000, category="Professional Services", division="Technology Services", award_date=date(2022, 2, 1)),
        _award("SW-1", "Software licensing and data migration.", 200000, category="Professional Services", division="Technology Services", award_date=date(2024, 2, 1)),
    ]
    solicitation = _solicitation("SOL-ROAD", "Road repairs, asphalt paving, curb repair, and traffic staging.")
    opportunity = evaluate_opportunities(profile, [solicitation], awards, TODAY)[0]
    attach_rag_evidence(profile, [opportunity], awards)
    model = train_award_history_market_model(profile, awards)
    apply_market_intelligence(profile, [opportunity], awards, model, TODAY)
    return profile, opportunity


def _solicitation(document_number: str, description: str) -> Solicitation:
    return Solicitation(
        document_number=document_number,
        solicitation_type="Request for Tender",
        category="Construction Services",
        description=description,
        division="Transportation Services",
        issue_date=TODAY,
        submission_deadline=date(2026, 6, 20),
    )


def _award(
    document_number: str,
    description: str,
    value: float,
    category: str = "Construction Services",
    division: str = "Transportation Services",
    award_date: date = TODAY,
) -> AwardRecord:
    return AwardRecord(
        document_number=document_number,
        solicitation_type="Request for Tender",
        category=category,
        supplier="Road Co",
        award_value=value,
        award_date=award_date,
        division=division,
        description=description,
    )


if __name__ == "__main__":
    unittest.main()
