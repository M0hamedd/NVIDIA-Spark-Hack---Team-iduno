from __future__ import annotations

import os
import time
import unittest
from datetime import date
from unittest.mock import patch

from contract_radar.models import (
    BusinessProfile,
    EvaluatedOpportunity,
    HistoricalComparison,
    RequirementExtraction,
    Solicitation,
)
from contract_radar.nemotron import enrich_top_opportunities, nemotron_status, reset_nim_preflight_cache


class NemotronFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_base_url = os.environ.get("NIM_BASE_URL")
        self._old_timeout = os.environ.get("NIM_TIMEOUT_SECONDS")
        self._old_preflight_timeout = os.environ.get("NIM_PREFLIGHT_TIMEOUT_SECONDS")
        os.environ["NIM_BASE_URL"] = "http://127.0.0.1:9/v1"
        os.environ["NIM_TIMEOUT_SECONDS"] = "0.05"
        os.environ["NIM_PREFLIGHT_TIMEOUT_SECONDS"] = "0.05"
        reset_nim_preflight_cache()

    def tearDown(self) -> None:
        if self._old_base_url is None:
            os.environ.pop("NIM_BASE_URL", None)
        else:
            os.environ["NIM_BASE_URL"] = self._old_base_url
        if self._old_timeout is None:
            os.environ.pop("NIM_TIMEOUT_SECONDS", None)
        else:
            os.environ["NIM_TIMEOUT_SECONDS"] = self._old_timeout
        if self._old_preflight_timeout is None:
            os.environ.pop("NIM_PREFLIGHT_TIMEOUT_SECONDS", None)
        else:
            os.environ["NIM_PREFLIGHT_TIMEOUT_SECONDS"] = self._old_preflight_timeout
        reset_nim_preflight_cache()

    def test_fallback_adds_usable_structured_requirements_without_nim(self) -> None:
        profile = BusinessProfile()
        opportunity = _opportunity()

        enriched, mode = enrich_top_opportunities(profile, [opportunity])

        self.assertEqual(mode, "deterministic_fallback")
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0].label, "Pursue")
        self.assertEqual(enriched[0].requirements.source, "deterministic_fallback")
        self.assertIn("HVAC maintenance", enriched[0].requirements.services)
        self.assertIn("building automation systems/BAS controls", enriched[0].requirements.services)
        self.assertEqual(enriched[0].requirements.deadline_risk, "Manageable")
        self.assertIn("GTA Mechanical & Controls Ltd.", enriched[0].nemotron_summary)
        self.assertIn("Historical signal", enriched[0].nemotron_summary)

    def test_local_nim_structured_response_is_validated(self) -> None:
        profile = BusinessProfile()
        response = {
            "services": ["HVAC preventative maintenance", "BAS controls"],
            "certifications": ["technician certification"],
            "documents": ["insurance", "WSIB"],
            "facility_signals": ["municipal facilities"],
            "risk_flags": ["after-hours response may be required"],
            "capacity_flags": ["multi-site scheduling review"],
            "procurement_type": "RFQ",
            "deadline_risk": "Manageable",
            "next_action": "Prepare owner review package.",
            "summary": "HVAC and controls service for municipal facilities.",
        }

        with patch("contract_radar.nemotron._nim_preflight", return_value={"available": True, "reason": "test"}):
            with patch("contract_radar.nemotron._chat_completion", return_value=__import__("json").dumps(response)):
                enriched, mode = enrich_top_opportunities(profile, [_opportunity()])

        self.assertEqual(mode, "local_nim")
        self.assertEqual(enriched[0].requirements.source, "local_nim")
        self.assertIn("BAS controls", enriched[0].requirements.services)
        self.assertEqual(enriched[0].requirements.next_action, "Prepare owner review package.")

    def test_to_dict_exposes_requirements_for_frontend(self) -> None:
        opportunity = _opportunity()
        opportunity.requirements = RequirementExtraction(
            source="deterministic_fallback",
            services=["HVAC maintenance"],
            deadline_risk="Manageable",
            next_action="Prepare owner review package.",
        )

        payload = opportunity.to_dict()

        self.assertIn("requirements", payload)
        self.assertIn("nemotron_requirements", payload)
        self.assertIn("capacity_assessment", payload)
        self.assertEqual(payload["requirements"]["services"], ["HVAC maintenance"])
        self.assertEqual(payload["capacity_assessment"]["pursuit_load"], "Clear")

    def test_status_is_available_without_nim(self) -> None:
        status = nemotron_status()

        self.assertEqual(status["fallback"], "deterministic_fallback")
        self.assertEqual(status["nim_mode"], "deterministic_fallback")
        self.assertFalse(status["available"])
        self.assertTrue(status["structured_extraction"])
        self.assertIn("model", status)

    def test_unavailable_nim_fast_fails_before_chat_completion(self) -> None:
        profile = BusinessProfile()
        opportunity = _opportunity()

        start = time.perf_counter()
        enriched, mode = enrich_top_opportunities(profile, [opportunity, opportunity, opportunity])
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 0.5)
        self.assertEqual(mode, "deterministic_fallback")
        self.assertEqual(len(enriched), 3)
        self.assertTrue(all(item.requirements.source == "deterministic_fallback" for item in enriched))


def _opportunity() -> EvaluatedOpportunity:
    return EvaluatedOpportunity(
        solicitation=Solicitation(
            document_number="RFQ-123",
            solicitation_type="RFQ",
            category="Facilities Maintenance",
            description="Preventative maintenance for HVAC systems and BAS controls",
            division="Corporate Real Estate Management",
            issue_date=date(2026, 5, 30),
            submission_deadline=date(2026, 6, 20),
            buyer_name="City Buyer",
        ),
        label="Pursue",
        rank_score=91,
        matched_terms=["preventative maintenance", "HVAC maintenance", "building automation systems/BAS controls"],
        missing_requirements=["confirm insurance certificate"],
        reasons=["RFQ format", "similar awards within preferred size"],
        days_until_deadline=21,
        historical=HistoricalComparison(
            similar_count=4,
            award_min=35000,
            award_median=72000,
            award_max=108000,
            accessibility="within small-business range",
        ),
    )


if __name__ == "__main__":
    unittest.main()
