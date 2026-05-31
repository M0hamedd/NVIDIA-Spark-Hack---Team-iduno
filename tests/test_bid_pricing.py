from __future__ import annotations

import unittest
from datetime import date

from contract_radar.bid_pricing import price_opportunity
from contract_radar.models import (
    BidRecommendation,
    EvaluatedOpportunity,
    HistoricalComparison,
    MarketFitSignal,
    RAGEvidence,
    Solicitation,
)
from contract_radar.profiles import get_supported_profile


TODAY = date(2026, 5, 30)


class BidPricingTests(unittest.TestCase):
    def test_pricing_engine_builds_cost_stack_and_optimizes_expected_profit(self) -> None:
        profile = get_supported_profile("road_civil_infrastructure")
        opportunity = EvaluatedOpportunity(
            solicitation=Solicitation(
                document_number="ROAD-PRICE",
                solicitation_type="Request for Tender",
                category="Construction Services",
                description="Road repairs, asphalt paving, bridge rehabilitation, and traffic staging at multiple locations.",
                division="Transportation Services",
                issue_date=TODAY,
                submission_deadline=date(2026, 6, 12),
            ),
            label="Pursue",
            rank_score=82,
            matched_terms=["road repairs", "asphalt paving", "traffic staging"],
            days_until_deadline=13,
            historical=HistoricalComparison(similar_count=5, award_min=500000, award_median=700000, award_max=900000),
            market_fit=MarketFitSignal(score=0.72, supplier_concentration={"top_supplier_share": 0.20}),
            bid_recommendation=BidRecommendation(
                source="trained_award_value_model",
                recommended_bid=760000,
                low_bid=650000,
                high_bid=880000,
                confidence="Moderate",
                median_award=710000,
            ),
            rag_evidence=RAGEvidence(value_median=720000, analogs=[{"document_number": "A1"}] * 4),
            fit_probability=0.72,
        )

        pricing = price_opportunity(profile, opportunity)
        payload = pricing.to_dict()

        self.assertEqual(payload["source"], "scope_cost_market_optimizer")
        self.assertGreater(payload["direct_cost"], 0)
        self.assertGreater(payload["contingency"], 0)
        self.assertGreater(payload["overhead"], 0)
        self.assertGreater(payload["recommended_bid"], payload["estimated_cost"])
        self.assertGreater(payload["expected_profit"], 0)
        self.assertEqual(len(payload["candidate_bids"]), 5)
        self.assertTrue(any("traffic staging" in item for item in payload["drivers"]))
        self.assertTrue(any("Cost stack" in item for item in payload["evidence"]))

    def test_pricing_engine_refuses_skipped_or_unpriced_opportunities(self) -> None:
        profile = get_supported_profile("parks_landscape")
        opportunity = EvaluatedOpportunity(
            solicitation=Solicitation(
                document_number="SKIP-PRICE",
                solicitation_type="RFP",
                category="Goods and Services",
                description="Software implementation.",
                division="Technology Services",
                issue_date=TODAY,
                submission_deadline=date(2026, 6, 12),
            ),
            label="Skip",
            rank_score=0,
        )

        pricing = price_opportunity(profile, opportunity)

        self.assertEqual(pricing.source, "skipped_by_bid_gates")
        self.assertEqual(pricing.recommended_bid, 0)


if __name__ == "__main__":
    unittest.main()
