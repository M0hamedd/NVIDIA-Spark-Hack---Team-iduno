from __future__ import annotations

import os
import time
import unittest
from datetime import date
from unittest.mock import patch
from urllib import error

from contract_radar.models import (
    BusinessProfile,
    EvaluatedOpportunity,
    HistoricalComparison,
    RequirementExtraction,
    Solicitation,
)
from contract_radar.nemotron import (
    SchemaRejectedError,
    enrich_top_opportunities,
    enrich_top_opportunities_with_stats,
    nemotron_status,
    reset_nim_preflight_cache,
)


class NemotronFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_base_url = os.environ.get("NIM_BASE_URL")
        self._old_timeout = os.environ.get("NIM_TIMEOUT_SECONDS")
        self._old_preflight_timeout = os.environ.get("NIM_PREFLIGHT_TIMEOUT_SECONDS")
        self._old_disabled = os.environ.get("CONTRACT_RADAR_DISABLE_NEMOTRON")
        os.environ["NIM_BASE_URL"] = "http://127.0.0.1:9/v1"
        os.environ["NIM_TIMEOUT_SECONDS"] = "0.05"
        os.environ["NIM_PREFLIGHT_TIMEOUT_SECONDS"] = "0.05"
        os.environ.pop("CONTRACT_RADAR_DISABLE_NEMOTRON", None)
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
        if self._old_disabled is None:
            os.environ.pop("CONTRACT_RADAR_DISABLE_NEMOTRON", None)
        else:
            os.environ["CONTRACT_RADAR_DISABLE_NEMOTRON"] = self._old_disabled
        reset_nim_preflight_cache()

    def test_fallback_adds_usable_structured_requirements_without_nim(self) -> None:
        profile = BusinessProfile()
        opportunity = _opportunity()

        enriched, mode = enrich_top_opportunities(profile, [opportunity])

        self.assertEqual(mode, "deterministic_fallback")
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0].label, "Pursue")
        self.assertEqual(enriched[0].requirements.source, "deterministic_fallback")
        self.assertIn("road repairs", enriched[0].requirements.services)
        self.assertIn("traffic staging", enriched[0].requirements.services)
        self.assertEqual(enriched[0].requirements.deadline_risk, "Manageable")
        self.assertIn("This is road repairs, sidewalk repairs, and traffic staging work", enriched[0].requirements.summary)
        self.assertEqual(enriched[0].opportunity_brief.source, "deterministic_fallback")
        self.assertIn("RFQ-123 is a Request for Tender from Transportation Services", enriched[0].opportunity_brief.fit_reason)
        self.assertIn("dataset description points to road repairs", enriched[0].opportunity_brief.fit_reason)
        self.assertNotIn("already has capability", enriched[0].opportunity_brief.fit_reason.lower())
        self.assertIn("official Toronto bidding portal", " ".join(enriched[0].opportunity_brief.next_steps))
        self.assertNotIn("Road repairs, sidewalk repairs, curb repair, asphalt paving", enriched[0].nemotron_summary)
        self.assertIn("Harbourfront Civil Works Ltd.", enriched[0].nemotron_summary)
        self.assertIn("Historical signal", enriched[0].nemotron_summary)

    def test_local_nim_structured_response_is_validated(self) -> None:
        profile = BusinessProfile()
        response = {
            "services": ["road repairs", "traffic staging"],
            "certifications": ["bonding capacity"],
            "documents": ["insurance", "WSIB"],
            "facility_signals": ["municipal road corridor"],
            "risk_flags": [],
            "capacity_flags": [],
            "procurement_type": "RFT",
            "deadline_risk": "Manageable",
            "next_action": "Prepare owner review package.",
            "summary": "Road and sidewalk repair work for municipal corridors.",
            "owner_brief": {
                "owner_summary": "Owner-ready road repair brief.",
                "fit_reason": "The profile has matching road repair capacity.",
                "blockers": [],
                "required_documents": ["insurance", "WSIB"],
                "missing_items": [],
                "clarification_questions": ["Confirm traffic staging requirements."],
                "next_steps": ["Prepare owner review package."],
                "buyer_email_draft": "Subject: Clarification for RFQ-123\n\nHello City Buyer,\n\nCan you confirm traffic staging requirements?\n\nThank you,\nHarbourfront Civil Works Ltd.",
            },
        }

        with patch("contract_radar.nemotron._nim_preflight", return_value={"available": True, "reason": "test"}):
            with patch("contract_radar.nemotron._chat_completion", return_value=__import__("json").dumps(response)):
                enriched, mode = enrich_top_opportunities(profile, [_opportunity()])

        self.assertEqual(mode, "local_nim")
        self.assertEqual(enriched[0].requirements.source, "local_nim")
        self.assertEqual(enriched[0].opportunity_brief.source, "local_nim")
        self.assertEqual(enriched[0].label, "Pursue")
        self.assertIn("traffic staging", enriched[0].requirements.services)
        self.assertEqual(enriched[0].requirements.next_action, "Prepare owner review package.")
        self.assertIn("Owner-ready road repair brief", enriched[0].opportunity_brief.owner_summary)
        self.assertIn("RFQ-123 is a RFT from Transportation Services", enriched[0].bid_fitness_trace.final_rationale)
        self.assertIn("dataset description points to road repairs", enriched[0].bid_fitness_trace.final_rationale)
        self.assertIn("Prepare owner review package", enriched[0].bid_fitness_trace.final_rationale)
        self.assertNotIn("Capability fit:", enriched[0].bid_fitness_trace.final_rationale)
        self.assertNotIn("already has capability", enriched[0].opportunity_brief.fit_reason.lower())

    def test_local_nim_blocker_downgrades_pursue_to_review(self) -> None:
        profile = BusinessProfile()
        response = {
            "services": ["road repairs", "traffic staging"],
            "certifications": ["bonding capacity"],
            "documents": ["insurance", "WSIB"],
            "facility_signals": ["municipal road corridor"],
            "risk_flags": ["bonding must be confirmed"],
            "capacity_flags": ["multi-site scheduling review"],
            "procurement_type": "RFT",
            "deadline_risk": "Manageable",
            "next_action": "Confirm bonding before pursuit.",
            "summary": "Road and sidewalk repair work for municipal corridors.",
            "owner_brief": {
                "owner_summary": "Road repair brief with a bonding blocker.",
                "fit_reason": "The profile has matching road repair capacity.",
                "blockers": ["bonding must be confirmed"],
                "required_documents": ["insurance", "WSIB", "bonding"],
                "missing_items": ["confirmed bonding capacity"],
                "clarification_questions": ["Is a bid bond mandatory?"],
                "next_steps": ["Confirm bonding capacity."],
                "buyer_email_draft": "Subject: Clarification for RFQ-123\n\nHello City Buyer,\n\nIs a bid bond mandatory?\n\nThank you,\nHarbourfront Civil Works Ltd.",
            },
        }

        with patch("contract_radar.nemotron._nim_preflight", return_value={"available": True, "reason": "test"}):
            with patch("contract_radar.nemotron._chat_completion", return_value=__import__("json").dumps(response)):
                enriched, mode = enrich_top_opportunities(profile, [_opportunity()])

        self.assertEqual(mode, "local_nim")
        self.assertEqual(enriched[0].pre_extraction_label, "Pursue")
        self.assertEqual(enriched[0].label, "Review")
        self.assertTrue(enriched[0].to_dict()["label_changed_by_extraction"])
        self.assertIn("confirmed bonding capacity", enriched[0].missing_requirements)
        self.assertIn("Nemotron extraction reconciliation rule", enriched[0].bid_fitness_trace.rules_triggered)

    def test_schema_rejection_retries_without_schema_once(self) -> None:
        profile = BusinessProfile()
        response = _nim_response()

        with patch("contract_radar.nemotron._nim_preflight", return_value={"available": True, "reason": "test"}):
            with patch(
                "contract_radar.nemotron._chat_completion",
                side_effect=[SchemaRejectedError("schema unsupported"), __import__("json").dumps(response)],
            ) as chat:
                enriched, mode = enrich_top_opportunities(profile, [_opportunity()])

        self.assertEqual(mode, "local_nim")
        self.assertEqual(enriched[0].requirements.source, "local_nim")
        self.assertEqual([call.kwargs["with_schema"] for call in chat.mock_calls], [True, False])

    def test_local_nim_listing_extraction_is_cached_across_profile_variants(self) -> None:
        first_profile = BusinessProfile(name="Harbourfront Civil Works Ltd.")
        second_profile = BusinessProfile(name="Variant Civil Works", max_contract_value=900000)
        response = _nim_response()

        with patch("contract_radar.nemotron._nim_preflight", return_value={"available": True, "reason": "test"}):
            with patch("contract_radar.nemotron._chat_completion", return_value=__import__("json").dumps(response)) as chat:
                first, first_mode = enrich_top_opportunities(first_profile, [_opportunity()])
                second, second_mode = enrich_top_opportunities(second_profile, [_opportunity()])

        self.assertEqual(first_mode, "local_nim")
        self.assertEqual(second_mode, "local_nim")
        self.assertEqual(chat.call_count, 1)
        self.assertIn("RFQ-123 is a RFT from Transportation Services", first[0].opportunity_brief.fit_reason)
        self.assertIn("RFQ-123 is a RFT from Transportation Services", second[0].opportunity_brief.fit_reason)
        self.assertEqual(second[0].opportunity_brief.source, "local_nim")

    def test_request_failure_does_not_retry_as_schema_fallback(self) -> None:
        profile = BusinessProfile()

        with patch("contract_radar.nemotron._nim_preflight", return_value={"available": True, "reason": "test"}):
            with patch(
                "contract_radar.nemotron._chat_completion",
                side_effect=RuntimeError("local NIM unavailable"),
            ) as chat:
                enriched, mode = enrich_top_opportunities(profile, [_opportunity()])

        self.assertEqual(mode, "deterministic_fallback")
        self.assertEqual(chat.call_count, 1)
        self.assertEqual(enriched[0].requirements.source, "deterministic_fallback")

    def test_partial_model_failure_reports_returned_fallback_briefs_only(self) -> None:
        profile = BusinessProfile()
        response = _nim_response()

        with patch("contract_radar.nemotron._nim_preflight", return_value={"available": True, "reason": "test"}):
            with patch(
                "contract_radar.nemotron._chat_completion",
                side_effect=[__import__("json").dumps(response), RuntimeError("local NIM unavailable")],
            ):
                second_opportunity = _opportunity()
                second_opportunity.solicitation.document_number = "RFQ-456"
                enriched, mode, stats = enrich_top_opportunities_with_stats(
                    profile,
                    [_opportunity(), second_opportunity],
                )

        self.assertEqual(mode, "deterministic_fallback")
        self.assertEqual(stats["model_calls_attempted"], 2)
        self.assertEqual(stats["model_calls_successful"], 0)
        self.assertEqual(stats["model_calls_failed"], 1)
        self.assertEqual(stats["briefs_generated"], 2)
        self.assertTrue(all(item.requirements.source == "deterministic_fallback" for item in enriched))

    def test_to_dict_exposes_requirements_for_frontend(self) -> None:
        opportunity = _opportunity()
        opportunity.requirements = RequirementExtraction(
            source="deterministic_fallback",
            services=["road repairs"],
            deadline_risk="Manageable",
            next_action="Prepare owner review package.",
        )

        payload = opportunity.to_dict()

        self.assertIn("requirements", payload)
        self.assertIn("nemotron_requirements", payload)
        self.assertIn("opportunity_brief", payload)
        self.assertIn("nemotron_brief", payload)
        self.assertIn("capacity_assessment", payload)
        self.assertEqual(payload["requirements"]["services"], ["road repairs"])
        self.assertEqual(payload["capacity_assessment"]["pursuit_load"], "Clear")

    def test_status_is_available_without_nim(self) -> None:
        status = nemotron_status()

        self.assertEqual(status["fallback"], "deterministic_fallback")
        self.assertEqual(status["nim_mode"], "deterministic_fallback")
        self.assertFalse(status["available"])
        self.assertTrue(status["structured_extraction"])
        self.assertIn("model", status)

    def test_preflight_requires_openai_compatible_http_endpoint(self) -> None:
        os.environ["NIM_BASE_URL"] = "http://127.0.0.1:30000/v1"
        reset_nim_preflight_cache()

        with patch(
            "contract_radar.nemotron.request.urlopen",
            side_effect=error.URLError("HTTP 404 from /models"),
        ):
            status = nemotron_status()

        self.assertFalse(status["available"])
        self.assertEqual(status["preflight"]["reason"], "http_preflight_failed")
        self.assertIn("/models", status["preflight"]["models_url"])

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

    def test_disable_nemotron_flag_forces_deterministic_fallback(self) -> None:
        os.environ["CONTRACT_RADAR_DISABLE_NEMOTRON"] = "1"
        reset_nim_preflight_cache()

        status = nemotron_status()
        enriched, mode = enrich_top_opportunities(BusinessProfile(), [_opportunity()])

        self.assertEqual(status["nim_mode"], "deterministic_fallback")
        self.assertEqual(status["preflight"]["reason"], "disabled_by_flag")
        self.assertEqual(mode, "deterministic_fallback")
        self.assertEqual(enriched[0].requirements.source, "deterministic_fallback")


def _opportunity() -> EvaluatedOpportunity:
    return EvaluatedOpportunity(
        solicitation=Solicitation(
            document_number="RFQ-123",
            solicitation_type="Request for Tender",
            category="Construction Services",
            description="Road repairs, sidewalk repairs, curb repair, asphalt paving, and traffic staging",
            division="Transportation Services",
            issue_date=date(2026, 5, 30),
            submission_deadline=date(2026, 6, 20),
            buyer_name="City Buyer",
        ),
        label="Pursue",
        rank_score=91,
        matched_terms=["road repairs", "sidewalk repairs", "traffic staging"],
        missing_requirements=["confirm bonding capacity"],
        reasons=["RFT format", "similar awards within preferred size"],
        days_until_deadline=21,
        historical=HistoricalComparison(
            similar_count=4,
            award_min=350000,
            award_median=720000,
            award_max=1080000,
            accessibility="within civil contractor range",
        ),
    )


def _nim_response() -> dict:
    return {
        "services": ["road repairs", "traffic staging"],
        "certifications": ["bonding capacity"],
        "documents": ["insurance", "WSIB"],
        "facility_signals": ["municipal road corridor"],
        "risk_flags": [],
        "capacity_flags": [],
        "procurement_type": "RFT",
        "deadline_risk": "Manageable",
        "next_action": "Prepare owner review package.",
        "summary": "Road and sidewalk repair work for municipal corridors.",
        "owner_brief": {
            "owner_summary": "Owner-ready road repair brief.",
            "fit_reason": "The profile has matching road repair capacity.",
            "blockers": [],
            "required_documents": ["insurance", "WSIB"],
            "missing_items": [],
            "clarification_questions": ["Confirm traffic staging requirements."],
            "next_steps": ["Prepare owner review package."],
            "buyer_email_draft": (
                "Subject: Clarification for RFQ-123\n\n"
                "Hello City Buyer,\n\n"
                "Can you confirm traffic staging requirements?\n\n"
                "Thank you,\nHarbourfront Civil Works Ltd."
            ),
        },
    }


if __name__ == "__main__":
    unittest.main()
