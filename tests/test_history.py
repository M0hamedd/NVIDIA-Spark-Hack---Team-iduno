from __future__ import annotations

import unittest
from datetime import date

from contract_radar.history import HistoricalOpportunitySummary, summarize_past_opportunities
from contract_radar.models import AwardRecord, BusinessProfile


class HistoricalOpportunitySummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = BusinessProfile(
            name="GTA Mechanical & Controls Ltd.",
            business_type="commercial HVAC and building automation contractor",
            max_contract_value=150000,
            skills=[
                "HVAC maintenance",
                "building automation systems",
                "boiler service",
                "chiller service",
                "emergency repairs",
                "preventative maintenance",
            ],
            missing_capabilities=["major construction bonding", "large design/build work"],
        )

    def test_summary_counts_realistic_past_awards_and_evidence(self) -> None:
        summary = summarize_past_opportunities(
            self.profile,
            [
                _award(
                    "AWD-HVAC-1",
                    85000,
                    "Facilities Management",
                    "Preventative HVAC maintenance and emergency repairs for municipal recreation centres.",
                    buyer="Maya Patel",
                ),
                _award(
                    "AWD-BAS-2",
                    125000,
                    "Facilities Management",
                    "Building automation systems controls service, boiler service, and chiller service.",
                    buyer="Maya Patel",
                ),
                _award(
                    "AWD-ROAD-3",
                    70000,
                    "Transportation Services",
                    "Road resurfacing, paving, curb repair, and asphalt supply.",
                    buyer="Road Buyer",
                ),
                _award(
                    "AWD-BIG-4",
                    900000,
                    "Corporate Real Estate Management",
                    "Major design-build construction of a recreation centre with mechanical systems.",
                    category="Construction Services",
                    solicitation_type="Request for Proposal",
                    buyer="Capital Projects",
                ),
            ],
        )

        self.assertIsInstance(summary, HistoricalOpportunitySummary)
        self.assertEqual(summary.realistic_count, 2)
        self.assertEqual([item["document_number"] for item in summary.sample_awards], ["AWD-BAS-2", "AWD-HVAC-1"])
        self.assertEqual(summary.award_value_range["min"], 85000)
        self.assertEqual(summary.award_value_range["median"], 105000)
        self.assertEqual(summary.award_value_range["max"], 125000)
        self.assertEqual(summary.common_divisions[0], {"name": "Facilities Management", "count": 2})
        self.assertEqual(summary.common_buyers[0], {"name": "Maya Patel", "count": 2})
        self.assertIn("hvac maintenance", summary.evidence_terms)
        self.assertIn("building automation systems", summary.evidence_terms)
        self.assertTrue(any("2 past awarded contracts" in line for line in summary.evidence))

    def test_summary_handles_no_value_matches(self) -> None:
        summary = summarize_past_opportunities(
            self.profile,
            [
                _award(
                    "AWD-NOVALUE",
                    0,
                    "Parks, Forestry and Recreation",
                    "Emergency repairs and preventative maintenance for HVAC systems.",
                )
            ],
        )

        self.assertEqual(summary.realistic_count, 1)
        self.assertEqual(summary.award_value_range, {"available_count": 0})
        self.assertEqual(summary.sample_awards[0]["award_value"], 0)

    def test_summary_returns_empty_shape_when_no_realistic_awards(self) -> None:
        summary = summarize_past_opportunities(
            self.profile,
            [
                _award(
                    "AWD-LEGAL",
                    40000,
                    "Legal Services",
                    "External legal counsel for employment litigation and policy advice.",
                    category="Professional Services",
                )
            ],
        )

        self.assertEqual(summary.to_dict()["realistic_count"], 0)
        self.assertEqual(summary.sample_awards, [])
        self.assertEqual(summary.award_value_range, {"available_count": 0})
        self.assertEqual(summary.common_divisions, [])
        self.assertEqual(summary.common_buyers, [])
        self.assertEqual(summary.evidence_terms, [])


def _award(
    document_number: str,
    award_value: float,
    division: str,
    description: str,
    category: str = "Goods and Services",
    solicitation_type: str = "Request for Quotation",
    buyer: str = "",
) -> AwardRecord:
    raw = {"Buyer Name": buyer} if buyer else {}
    return AwardRecord(
        document_number=document_number,
        solicitation_type=solicitation_type,
        category=category,
        supplier="Toronto Vendor Inc.",
        award_value=award_value,
        award_date=date(2025, 6, 1),
        division=division,
        description=description,
        raw=raw,
    )


if __name__ == "__main__":
    unittest.main()
