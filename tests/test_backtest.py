from __future__ import annotations

import unittest
from datetime import date

from contract_radar.backtest import scorecard_from_evaluated
from contract_radar.history import summarize_past_opportunities
from contract_radar.matcher import evaluate_opportunities
from contract_radar.models import AwardRecord, BusinessProfile, Solicitation


TODAY = date(2026, 5, 30)


class BacktestScorecardTests(unittest.TestCase):
    def test_scorecard_counts_true_fit_false_positive_and_capacity_downgrade(self) -> None:
        profile = BusinessProfile(active_pursuit_count=3, max_active_pursuits=3)
        solicitations = [
            _solicitation(
                "RFQ-TRUE",
                "Request for Tender",
                "Construction Services",
                "Road repairs sidewalk repairs curb repair asphalt paving and traffic staging for municipal road corridors",
                date(2026, 6, 20),
            ),
            _solicitation(
                "RFQ-FALSE",
                "Request for Proposal",
                "Professional Services",
                "Cloud-based road asset management software implementation with data migration and licensing",
                date(2026, 6, 20),
            ),
            _solicitation(
                "RFQ-CAPACITY",
                "Request for Tender",
                "Construction Services",
                "Road repairs sidewalk repairs curb repair asphalt paving and traffic staging for municipal road corridors",
                date(2026, 6, 2),
            ),
        ]
        awards = [
            _award(
                "AWD-ROAD",
                640000,
                "Transportation Services",
                "Road repairs sidewalk repairs curb repair asphalt paving and traffic staging",
            ),
            _award(
                "AWD-BRIDGE",
                1180000,
                "Engineering & Construction Services",
                "Bridge rehabilitation traffic staging and civil infrastructure construction",
            ),
        ]

        evaluated = evaluate_opportunities(profile, solicitations, awards, TODAY)
        historical_summary = summarize_past_opportunities(profile, awards).to_dict()
        scorecard = scorecard_from_evaluated(profile, evaluated, historical_summary)

        self.assertGreaterEqual(scorecard["actionable_count"], 1)
        self.assertGreaterEqual(scorecard["false_positives_skipped"], 1)
        self.assertGreaterEqual(scorecard["capacity_downgrades"], 1)
        self.assertGreaterEqual(scorecard["similar_awards_grounded"], 1)
        self.assertEqual(scorecard["best_current_opportunity"]["document_number"], "RFQ-TRUE")
        self.assertTrue(scorecard["best_current_opportunity"]["decision_reason"])
        self.assertGreaterEqual(len(scorecard["similar_award_examples"]), 1)
        self.assertTrue(scorecard["similar_award_range"])
        self.assertGreaterEqual(scorecard["false_positive_categories"][0]["count"], 1)
        self.assertEqual(scorecard["false_positive_categories"][0]["category"], "Professional Services")
        self.assertGreaterEqual(scorecard["capacity_downgrade_reasons"][0]["count"], 1)
        self.assertTrue(scorecard["capacity_examples"][0]["capacity_warnings"])
        self.assertIn("data-backed bid signal", scorecard["top_insight"])
        self.assertIn("Transportation Services", scorecard["top_insight"])
        self.assertIn("$640,000-$1,180,000", scorecard["top_insight"])
        self.assertIn("Professional Services/pure software implementation", scorecard["top_insight"])
        self.assertIn("Action: prioritize owner review", scorecard["top_insight"])


def _solicitation(
    document_number: str,
    solicitation_type: str,
    category: str,
    description: str,
    deadline: date,
) -> Solicitation:
    return Solicitation(
        document_number=document_number,
        solicitation_type=solicitation_type,
        category=category,
        description=description,
        division="Transportation Services",
        issue_date=TODAY,
        submission_deadline=deadline,
    )


def _award(document_number: str, value: float, division: str, description: str) -> AwardRecord:
    return AwardRecord(
        document_number=document_number,
        solicitation_type="Request for Tender",
        category="Construction Services",
        supplier="Local Civil Vendor",
        award_value=value,
        award_date=date(2025, 5, 30),
        division=division,
        description=description,
    )


if __name__ == "__main__":
    unittest.main()
