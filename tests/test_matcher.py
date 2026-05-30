from __future__ import annotations

import unittest
from datetime import date

from contract_radar.history import compare_history
from contract_radar.matcher import evaluate_opportunities
from contract_radar.models import AwardRecord, BusinessProfile, Solicitation


TODAY = date(2026, 5, 30)


class MatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = BusinessProfile()
        self.awards = [
            AwardRecord(
                document_number="AWD-1",
                solicitation_type="RFQ",
                category="Goods and Services",
                supplier="GTA Mechanical Services",
                award_value=145000,
                award_date=date(2025, 6, 1),
                division="Facilities Management",
                description="HVAC maintenance and emergency repairs for municipal public facilities",
            ),
            AwardRecord(
                document_number="AWD-2",
                solicitation_type="Request for Quotation",
                category="Goods and Services",
                supplier="Metro Controls Ltd.",
                award_value=220000,
                award_date=date(2025, 10, 1),
                division="Facilities Management",
                description="Building automation systems BAS controls boiler service and chiller service",
            ),
            AwardRecord(
                document_number="AWD-3",
                solicitation_type="RFP",
                category="Construction Services",
                supplier="Major Builder",
                award_value=950000,
                award_date=date(2024, 9, 1),
                division="Corporate Real Estate Management",
                description="Design build renovation and construction management",
            ),
        ]

    def test_relevant_rfq_is_pursue(self) -> None:
        solicitation = _solicitation(
            document_number="RFQ-1",
            solicitation_type="RFQ",
            category="Goods and Services",
            description="HVAC maintenance BAS controls boiler service and emergency repairs for municipal facilities",
            division="Facilities Management",
            deadline=date(2026, 6, 20),
        )

        result = evaluate_opportunities(self.profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Pursue")
        self.assertIn("HVAC maintenance", result.matched_terms)
        self.assertGreater(result.historical.similar_count, 0)
        self.assertLessEqual(result.historical.award_median, self.profile.max_contract_value)
        self.assertTrue(any("Core Fit:" in reason for reason in result.reasons))
        self.assertEqual(result.capacity_assessment.pursuit_load, "Clear")
        self.assertEqual(result.capacity_assessment.recommended_action, "Pursue Now")

    def test_relevant_close_deadline_is_pursue_with_deadline_risk(self) -> None:
        solicitation = _solicitation(
            document_number="RFQ-URGENT",
            solicitation_type="Request for Quotation",
            category="Goods and Services",
            description="HVAC maintenance emergency repairs and BAS controls",
            division="Facilities Management",
            deadline=date(2026, 6, 2),
        )

        result = evaluate_opportunities(self.profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Pursue")
        self.assertEqual(result.days_until_deadline, 3)
        self.assertTrue(any("Deadline Risk: Critical." == reason for reason in result.reasons))

    def test_busy_capacity_warning_does_not_hide_strong_fit(self) -> None:
        profile = BusinessProfile(active_pursuit_count=2, max_active_pursuits=3)
        solicitation = _solicitation(
            document_number="RFQ-BUSY",
            solicitation_type="RFQ",
            category="Goods and Services",
            description="HVAC maintenance BAS controls boiler service and emergency repairs for municipal facilities",
            division="Facilities Management",
            deadline=date(2026, 6, 20),
        )

        result = evaluate_opportunities(profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Pursue")
        self.assertEqual(result.capacity_assessment.pursuit_load, "Busy")
        self.assertEqual(result.capacity_assessment.recommended_action, "Pursue Now")
        self.assertTrue(result.capacity_assessment.warnings)

    def test_overloaded_close_deadline_downgrades_strong_fit_to_review(self) -> None:
        profile = BusinessProfile(active_pursuit_count=3, max_active_pursuits=3)
        solicitation = _solicitation(
            document_number="RFQ-OVERLOADED",
            solicitation_type="Request for Quotation",
            category="Goods and Services",
            description="HVAC maintenance BAS controls boiler service and emergency repairs for municipal facilities",
            division="Facilities Management",
            deadline=date(2026, 6, 2),
        )

        result = evaluate_opportunities(profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Review")
        self.assertEqual(result.capacity_assessment.pursuit_load, "Overloaded")
        self.assertEqual(result.capacity_assessment.response_capacity, "At Risk")
        self.assertEqual(result.capacity_assessment.recommended_action, "Pursue After Review")
        self.assertTrue(any("Capacity warning" in reason for reason in result.reasons))

    def test_expired_is_skip(self) -> None:
        solicitation = _solicitation(
            document_number="OLD-1",
            solicitation_type="RFQ",
            category="Goods and Services",
            description="HVAC maintenance and boiler service",
            deadline=date(2026, 5, 1),
        )

        result = evaluate_opportunities(self.profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Skip")
        self.assertIn("expired", result.rejection_reasons)

    def test_unrelated_is_skip(self) -> None:
        solicitation = _solicitation(
            document_number="IT-1",
            solicitation_type="RFQ",
            category="Information Technology",
            description="Supply laptop computers and cloud software subscriptions",
            deadline=date(2026, 6, 20),
        )

        result = evaluate_opportunities(self.profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Skip")
        self.assertIn("wrong service/category", result.rejection_reasons)

    def test_large_construction_scope_requires_review_or_skip(self) -> None:
        solicitation = _solicitation(
            document_number="RFP-1",
            solicitation_type="RFP",
            category="Construction Services",
            description=(
                "Design-build renovation with HVAC maintenance boiler service "
                "mechanical repairs and building automation systems/BAS controls"
            ),
            division="Corporate Real Estate Management",
            deadline=date(2026, 6, 30),
        )

        result = evaluate_opportunities(self.profile, [solicitation], self.awards, TODAY)[0]

        self.assertIn(result.label, {"Review", "Skip"})
        self.assertTrue(
            {"complex solicitation type", "large construction/design-build scope"}
            & set(result.rejection_reasons)
        )

    def test_relevant_weak_opportunity_is_monitor(self) -> None:
        solicitation = _solicitation(
            document_number="MONITOR-1",
            solicitation_type="Request for Information",
            category="Vendor Registry",
            description="Mechanical repairs vendor roster for future municipal public facilities",
            division="Purchasing and Materials Management",
            deadline=date(2026, 6, 25),
        )

        result = evaluate_opportunities(self.profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Monitor")

    def test_generic_maintenance_match_is_not_pursue(self) -> None:
        solicitation = _solicitation(
            document_number="GENERIC-1",
            solicitation_type="RFQ",
            category="Goods and Services",
            description=(
                "Preventative maintenance and emergency repair services for kitchen equipment "
                "including specialized tools and consumables"
            ),
            division="Purchasing and Materials Management",
            deadline=date(2026, 6, 25),
        )

        result = evaluate_opportunities(self.profile, [solicitation], self.awards, TODAY)[0]

        self.assertNotEqual(result.label, "Pursue")
        self.assertIn(result.label, {"Monitor", "Skip"})

    def test_frontend_profile_rejects_kitchen_equipment_false_positive(self) -> None:
        profile = BusinessProfile(
            max_contract_value=750000,
            skills=[
                "HVAC maintenance",
                "building automation systems",
                "BAS controls",
                "boiler service",
                "chiller service",
                "preventative maintenance",
                "emergency repair",
                "municipal facility service",
            ],
            missing_capabilities=[
                "kitchen equipment",
                "road paving",
                "legal services",
                "food supply",
                "large design/build construction",
            ],
        )
        solicitation = _solicitation(
            document_number="KITCHEN-1",
            solicitation_type="RFQ",
            category="Goods and Services",
            description=(
                "Preventative maintenance, emergency repair services, and corrective "
                "maintenance for kitchen equipment, inclusive of consumables and specialized tools."
            ),
            deadline=date(2026, 6, 20),
        )

        result = evaluate_opportunities(profile, [solicitation], self.awards, TODAY)[0]

        self.assertEqual(result.label, "Skip")
        self.assertIn("kitchen equipment", result.missing_requirements)

    def test_priority_modes_change_order_without_changing_labels(self) -> None:
        best_fit = _solicitation(
            document_number="FIT-1",
            solicitation_type="RFQ",
            category="Goods and Services",
            description=(
                "HVAC maintenance emergency repairs boiler service and chiller service "
                "for municipal public facilities"
            ),
            division="Facilities Management",
            deadline=date(2026, 6, 20),
        )
        higher_value = _solicitation(
            document_number="VALUE-1",
            solicitation_type="RFQ",
            category="Goods and Services",
            description=(
                "Building automation systems/BAS controls energy retrofit support and "
                "municipal/public facility service"
            ),
            division="Environment and Climate",
            deadline=date(2026, 6, 20),
        )
        high_value_awards = [
            *self.awards,
            AwardRecord(
                document_number="AWD-4",
                solicitation_type="RFQ",
                category="Goods and Services",
                supplier="Integrated Building Controls",
                award_value=330000,
                award_date=date(2025, 8, 1),
                division="Environment and Climate",
                description=(
                    "Building automation systems BAS controls energy retrofit support and "
                    "municipal public facility service"
                ),
            ),
        ]

        fit_order = evaluate_opportunities(
            self.profile,
            [higher_value, best_fit],
            high_value_awards,
            TODAY,
            priority_mode="best_fit",
        )
        value_order = evaluate_opportunities(
            self.profile,
            [higher_value, best_fit],
            high_value_awards,
            TODAY,
            priority_mode="highest_value",
        )

        self.assertEqual(fit_order[0].solicitation.document_number, "FIT-1")
        self.assertEqual(value_order[0].solicitation.document_number, "VALUE-1")
        self.assertEqual(
            {item.solicitation.document_number: item.label for item in fit_order},
            {item.solicitation.document_number: item.label for item in value_order},
        )

    def test_history_returns_range_and_accessibility(self) -> None:
        solicitation = _solicitation(
            document_number="RFQ-HISTORY",
            solicitation_type="RFQ",
            category="Goods and Services",
            description="HVAC maintenance BAS controls boiler service and chiller service",
            division="Facilities Management",
            deadline=date(2026, 6, 20),
        )

        comparison = compare_history(solicitation, self.awards, self.profile)

        self.assertGreaterEqual(comparison.similar_count, 2)
        self.assertEqual(comparison.award_min, 145000)
        self.assertEqual(comparison.award_max, 220000)
        self.assertEqual(comparison.award_median, 182500)
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


if __name__ == "__main__":
    unittest.main()
