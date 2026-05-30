from __future__ import annotations

import unittest
from datetime import date

from contract_radar.history import HistoricalOpportunitySummary, summarize_past_opportunities
from contract_radar.models import AwardRecord
from contract_radar.profiles import get_supported_profile


class HistoricalOpportunitySummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = get_supported_profile("road_civil_infrastructure")

    def test_summary_counts_realistic_past_awards_and_evidence(self) -> None:
        summary = summarize_past_opportunities(
            self.profile,
            [
                _award(
                    "AWD-ROAD-1",
                    640000,
                    "Transportation Services",
                    "Road repairs, sidewalk repairs, curb repair, asphalt paving, and traffic staging.",
                    buyer="Road Buyer",
                ),
                _award(
                    "AWD-BRIDGE-2",
                    1180000,
                    "Engineering & Construction Services",
                    "Bridge rehabilitation, traffic staging, and civil infrastructure construction.",
                    buyer="Bridge Buyer",
                ),
                _award(
                    "AWD-PARK-3",
                    270000,
                    "Parks, Forestry & Recreation",
                    "Park improvements, playground installation, landscaping, planting, and site furnishings.",
                    buyer="Parks Buyer",
                ),
                _award(
                    "AWD-BIG-4",
                    5600000,
                    "Corporate Real Estate Management",
                    "Design-build construction of a new facility with full design and construction scope.",
                    category="Construction Services",
                    solicitation_type="Request for Proposal",
                    buyer="Capital Projects",
                ),
            ],
        )

        self.assertIsInstance(summary, HistoricalOpportunitySummary)
        self.assertEqual(summary.realistic_count, 2)
        self.assertEqual(
            {item["document_number"] for item in summary.sample_awards},
            {"AWD-BRIDGE-2", "AWD-ROAD-1"},
        )
        self.assertEqual(summary.award_value_range["min"], 640000)
        self.assertEqual(summary.award_value_range["median"], 910000)
        self.assertEqual(summary.award_value_range["max"], 1180000)
        self.assertEqual(
            {item["name"] for item in summary.common_divisions},
            {"Engineering & Construction Services", "Transportation Services"},
        )
        self.assertIn("road repairs", summary.evidence_terms)
        self.assertIn("traffic staging", summary.evidence_terms)
        self.assertTrue(any("2 past awarded contracts" in line for line in summary.evidence))

    def test_summary_handles_no_value_matches(self) -> None:
        summary = summarize_past_opportunities(
            self.profile,
            [
                _award(
                    "AWD-NOVALUE",
                    0,
                    "Transportation Services",
                    "Road repairs, sidewalk repairs, and curb repair.",
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
    category: str = "Construction Services",
    solicitation_type: str = "Request for Tender",
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
