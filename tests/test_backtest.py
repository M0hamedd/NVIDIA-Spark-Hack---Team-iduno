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
                "Request for Quotation",
                "Goods and Services",
                "HVAC maintenance BAS controls boiler service and emergency repairs for municipal facilities",
                date(2026, 6, 20),
            ),
            _solicitation(
                "RFQ-FALSE",
                "Request for Quotation",
                "Goods and Services",
                "Preventative maintenance and emergency repair services for kitchen equipment",
                date(2026, 6, 20),
            ),
            _solicitation(
                "RFQ-CAPACITY",
                "Request for Quotation",
                "Goods and Services",
                "HVAC maintenance BAS controls boiler service and emergency repairs for municipal facilities",
                date(2026, 6, 2),
            ),
        ]
        awards = [
            _award(
                "AWD-HVAC",
                125000,
                "Facilities Management",
                "HVAC maintenance BAS controls boiler service for municipal facilities",
            ),
            _award(
                "AWD-CONTROLS",
                180000,
                "Facilities Management",
                "Building automation systems BAS controls and emergency mechanical repairs",
            ),
        ]

        evaluated = evaluate_opportunities(profile, solicitations, awards, TODAY)
        historical_summary = summarize_past_opportunities(profile, awards).to_dict()
        scorecard = scorecard_from_evaluated(profile, evaluated, historical_summary)

        self.assertGreaterEqual(scorecard["actionable_count"], 1)
        self.assertGreaterEqual(scorecard["false_positives_skipped"], 1)
        self.assertGreaterEqual(scorecard["capacity_downgrades"], 1)
        self.assertGreaterEqual(scorecard["similar_awards_grounded"], 1)
        self.assertIn("non-obvious revenue signal", scorecard["top_insight"])


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
        division="Facilities Management",
        issue_date=TODAY,
        submission_deadline=deadline,
    )


def _award(document_number: str, value: float, division: str, description: str) -> AwardRecord:
    return AwardRecord(
        document_number=document_number,
        solicitation_type="Request for Quotation",
        category="Goods and Services",
        supplier="Local HVAC Vendor",
        award_value=value,
        award_date=date(2025, 5, 30),
        division=division,
        description=description,
    )


if __name__ == "__main__":
    unittest.main()
