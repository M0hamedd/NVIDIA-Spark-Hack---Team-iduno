from __future__ import annotations

import unittest
from datetime import date

from contract_radar.history import compare_history
from contract_radar.matcher import evaluate_opportunities
from contract_radar.models import AwardRecord, Solicitation
from contract_radar.profiles import get_supported_profile


TODAY = date(2026, 5, 30)


class MatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.road_profile = get_supported_profile("road_civil_infrastructure")
        self.parks_profile = get_supported_profile("parks_landscape")
        self.engineering_profile = get_supported_profile("professional_engineering_design")
        self.awards = [
            _award(
                "AWD-ROAD-1",
                640000,
                "Transportation Services",
                "Road repairs, sidewalk repairs, curb repair, asphalt paving, and traffic staging for municipal road corridors.",
                category="Construction Services",
                solicitation_type="Request for Tender",
            ),
            _award(
                "AWD-BRIDGE-2",
                1180000,
                "Engineering & Construction Services",
                "Bridge rehabilitation with deck repairs, traffic staging, concrete curb work, and civil infrastructure construction.",
                category="Construction Services",
                solicitation_type="Request for Tender",
            ),
            _award(
                "AWD-PARK-1",
                310000,
                "Parks, Forestry & Recreation",
                "Park improvements, playground installation, splash pad repairs, planting, site furnishings, and fencing.",
                category="Construction Services",
                solicitation_type="Request for Tender",
            ),
            _award(
                "AWD-ARBOR-2",
                95000,
                "Parks, Forestry & Recreation",
                "Tree and arborist services, trail repairs, sports field maintenance, and public realm maintenance.",
                category="Goods and Services",
                solicitation_type="Request for Quotation",
            ),
            _award(
                "AWD-ENG-1",
                520000,
                "Engineering & Construction Services",
                "Professional consulting engineering services for preliminary design, detailed design, tender preparation, and contract administration.",
                category="Professional Services",
                solicitation_type="Request for Proposal",
            ),
            _award(
                "AWD-DESIGN-2",
                360000,
                "Parks, Forestry & Recreation",
                "Park and public realm design, accessibility upgrades, facility condition assessments, and construction inspection.",
                category="Professional Services",
                solicitation_type="Request for Proposal",
            ),
        ]

    def test_road_civil_tender_is_pursue(self) -> None:
        solicitation = _solicitation(
            document_number="RFT-ROAD-1",
            solicitation_type="Request for Tender",
            category="Construction Services",
            description=(
                "Road repairs, sidewalk repairs, curb repair, asphalt paving, and traffic staging "
                "for multiple municipal road corridors."
            ),
            division="Transportation Services",
            deadline=date(2026, 6, 20),
        )

        result = evaluate_opportunities(self.road_profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Pursue")
        self.assertIn("road repairs", result.matched_terms)
        self.assertGreater(result.historical.similar_count, 0)
        self.assertLessEqual(result.historical.award_median, self.road_profile.max_contract_value)
        self.assertTrue(any("Core Fit:" in reason for reason in result.reasons))
        self.assertEqual(result.capacity_assessment.recommended_action, "Pursue Now")
        trace = result.to_dict()["bid_fitness_trace"]
        self.assertTrue(trace["positive_signals"])
        self.assertTrue(trace["capacity_gates"])
        self.assertEqual(trace["scorecard_labels"]["Core Fit"], "Strong")
        self.assertEqual(trace["scorecard_labels"]["Recommended Action"], "Pursue Now")
        self.assertIn("Pursue:", trace["final_rationale"])

    def test_overloaded_close_deadline_downgrades_strong_fit_to_review(self) -> None:
        profile = get_supported_profile("road_civil_infrastructure")
        profile.active_pursuit_count = profile.max_active_pursuits
        solicitation = _solicitation(
            document_number="RFT-ROAD-URGENT",
            solicitation_type="Request for Tender",
            category="Construction Services",
            description="Road repairs sidewalk repairs curb repair asphalt paving and traffic staging.",
            division="Transportation Services",
            deadline=date(2026, 6, 2),
        )

        result = evaluate_opportunities(profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Review")
        self.assertEqual(result.capacity_assessment.pursuit_load, "Overloaded")
        self.assertEqual(result.capacity_assessment.response_capacity, "At Risk")
        self.assertEqual(result.capacity_assessment.recommended_action, "Pursue After Review")
        self.assertTrue(any("Capacity warning" in reason for reason in result.reasons))
        trace = result.to_dict()["bid_fitness_trace"]
        self.assertTrue(any("Pursuit Load: Overloaded" in warning for warning in trace["soft_warnings"]))
        self.assertTrue(any("Response Capacity: At Risk" in warning for warning in trace["soft_warnings"]))
        self.assertEqual(trace["scorecard_labels"]["Recommended Action"], "Pursue After Review")
        self.assertIn("Capacity gate: pursue after review", trace["rules_triggered"])

    def test_expired_is_skip(self) -> None:
        solicitation = _solicitation(
            document_number="OLD-ROAD",
            solicitation_type="Request for Tender",
            category="Construction Services",
            description="Road repairs, sidewalk repairs, and curb repair.",
            deadline=date(2026, 5, 1),
        )

        result = evaluate_opportunities(self.road_profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Skip")
        self.assertIn("expired", result.rejection_reasons)

    def test_road_profile_rejects_pure_software_mismatch(self) -> None:
        solicitation = _solicitation(
            document_number="IT-1",
            solicitation_type="Request for Proposal",
            category="Professional Services",
            description="Cloud-based software implementation including data migration, licensing, and training.",
            deadline=date(2026, 6, 20),
            division="Technology Services",
        )

        result = evaluate_opportunities(self.road_profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Skip")
        self.assertIn("wrong service/category", result.rejection_reasons)

    def test_parks_landscape_rejects_non_park_road_false_positive(self) -> None:
        solicitation = _solicitation(
            document_number="ROAD-LANDSCAPE",
            solicitation_type="Request for Tender",
            category="Construction Services",
            description=(
                "Major road construction, sewer rehabilitation, curb repair, asphalt paving, "
                "and streetscape landscaping for arterial road corridors."
            ),
            division="Transportation Services",
            deadline=date(2026, 6, 20),
        )

        result = evaluate_opportunities(self.parks_profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Skip")
        self.assertIn("blocked capability mismatch", result.rejection_reasons)
        self.assertIn("major road construction", result.missing_requirements)
        trace = result.to_dict()["bid_fitness_trace"]
        self.assertTrue(trace["hard_blockers"])
        self.assertTrue(any("major road construction" in blocker for blocker in trace["hard_blockers"]))
        self.assertIn("False-positive blocker: blocked capability mismatch", trace["rules_triggered"])

    def test_engineering_design_rejects_construction_only_bid(self) -> None:
        solicitation = _solicitation(
            document_number="CONSTRUCTION-ONLY",
            solicitation_type="Request for Tender",
            category="Construction Services",
            description="Road paving, sidewalk construction, and curb repair by a general contractor.",
            division="Transportation Services",
            deadline=date(2026, 6, 20),
        )

        result = evaluate_opportunities(self.engineering_profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Skip")
        self.assertIn("wrong service/category", result.rejection_reasons)

    def test_relevant_weak_opportunity_is_monitor(self) -> None:
        solicitation = _solicitation(
            document_number="MONITOR-1",
            solicitation_type="Request for Information",
            category="Vendor Registry",
            description="Future vendor registry for civil infrastructure contractor updates.",
            division="Purchasing and Materials Management",
            deadline=date(2026, 6, 25),
        )

        result = evaluate_opportunities(self.road_profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Monitor")

    def test_priority_modes_change_order_without_changing_labels(self) -> None:
        best_fit = _solicitation(
            document_number="FIT-1",
            solicitation_type="Request for Tender",
            category="Construction Services",
            description="Road repairs sidewalk repairs curb repair and asphalt paving for city corridors.",
            division="Transportation Services",
            deadline=date(2026, 6, 20),
        )
        higher_value = _solicitation(
            document_number="VALUE-1",
            solicitation_type="Request for Tender",
            category="Construction Services",
            description="Bridge rehabilitation traffic staging and civil infrastructure construction.",
            division="Engineering & Construction Services",
            deadline=date(2026, 6, 20),
        )

        fit_order = evaluate_opportunities(
            self.road_profile,
            [higher_value, best_fit],
            self.awards,
            TODAY,
            priority_mode="best_fit",
        )
        value_order = evaluate_opportunities(
            self.road_profile,
            [higher_value, best_fit],
            self.awards,
            TODAY,
            priority_mode="highest_value",
        )

        self.assertEqual(fit_order[0].solicitation.document_number, "FIT-1")
        self.assertEqual(value_order[0].solicitation.document_number, "VALUE-1")
        self.assertEqual(
            {item.solicitation.document_number: item.label for item in fit_order},
            {item.solicitation.document_number: item.label for item in value_order},
        )

    def test_profile_switching_changes_top_ranking(self) -> None:
        road = _solicitation(
            "ROAD-FIT",
            "Request for Tender",
            "Construction Services",
            "Road repairs sidewalk repairs curb repair asphalt paving and traffic staging.",
            date(2026, 6, 20),
            "Transportation Services",
        )
        parks = _solicitation(
            "PARK-FIT",
            "Request for Tender",
            "Construction Services",
            "Park improvements playground installation splash pad repairs landscaping and planting.",
            date(2026, 6, 20),
            "Parks, Forestry & Recreation",
        )
        engineering = _solicitation(
            "ENG-FIT",
            "Request for Proposal",
            "Professional Services",
            "Professional consulting engineering services for preliminary design detailed design and tender preparation.",
            date(2026, 6, 20),
            "Engineering & Construction Services",
        )

        road_order = evaluate_opportunities(self.road_profile, [parks, engineering, road], self.awards, TODAY)
        parks_order = evaluate_opportunities(self.parks_profile, [road, engineering, parks], self.awards, TODAY)
        eng_order = evaluate_opportunities(self.engineering_profile, [road, parks, engineering], self.awards, TODAY)

        self.assertEqual(road_order[0].solicitation.document_number, "ROAD-FIT")
        self.assertEqual(parks_order[0].solicitation.document_number, "PARK-FIT")
        self.assertEqual(eng_order[0].solicitation.document_number, "ENG-FIT")

    def test_history_returns_range_and_accessibility(self) -> None:
        solicitation = _solicitation(
            document_number="RFT-HISTORY",
            solicitation_type="Request for Tender",
            category="Construction Services",
            description="Road repairs sidewalk repairs curb repair asphalt paving and traffic staging.",
            division="Transportation Services",
            deadline=date(2026, 6, 20),
        )

        comparison = compare_history(solicitation, self.awards, self.road_profile)

        self.assertGreaterEqual(comparison.similar_count, 1)
        self.assertEqual(comparison.award_min, 640000)
        self.assertIn("accessible", comparison.accessibility)


def _solicitation(
    document_number: str,
    solicitation_type: str,
    category: str,
    description: str,
    deadline: date,
    division: str = "Purchasing and Materials Management",
) -> Solicitation:
    return Solicitation(
        document_number=document_number,
        solicitation_type=solicitation_type,
        category=category,
        description=description,
        division=division,
        issue_date=date(2026, 5, 20),
        submission_deadline=deadline,
    )


def _award(
    document_number: str,
    award_value: float,
    division: str,
    description: str,
    category: str = "Construction Services",
    solicitation_type: str = "Request for Tender",
) -> AwardRecord:
    return AwardRecord(
        document_number=document_number,
        solicitation_type=solicitation_type,
        category=category,
        supplier="Toronto Vendor Inc.",
        award_value=award_value,
        award_date=date(2025, 6, 1),
        division=division,
        description=description,
    )


if __name__ == "__main__":
    unittest.main()
