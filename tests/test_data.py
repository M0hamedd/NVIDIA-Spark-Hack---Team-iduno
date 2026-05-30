from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from contract_radar import config
from contract_radar.data import _prepare_records
from contract_radar.data import load_procurement_data
from contract_radar.models import AwardRecord, BusinessProfile, Solicitation
from contract_radar.matcher import evaluate_opportunities
from contract_radar.sample_data import SAMPLE_SOLICITATION_RECORDS, sample_awards, sample_solicitations


def _cudf_available() -> bool:
    try:
        __import__("cudf")
    except Exception:
        return False
    return True


class ProcurementDataTests(unittest.TestCase):
    def test_sample_records_convert_to_models(self) -> None:
        solicitations = sample_solicitations()
        awards = sample_awards()

        self.assertTrue(all(isinstance(item, Solicitation) for item in solicitations))
        self.assertTrue(all(isinstance(item, AwardRecord) for item in awards))
        self.assertEqual(solicitations[0].document_number, "RFQ-2026-RC-101")
        self.assertIn("road resurfacing", solicitations[0].description.lower())
        self.assertIn("asphalt paving", solicitations[0].description.lower())
        self.assertGreater(awards[0].award_value, 0)

    def test_sample_records_cover_three_demo_profiles(self) -> None:
        roles_by_profile: dict[str, set[str]] = {}
        for record in SAMPLE_SOLICITATION_RECORDS:
            profile = str(record.get("Demo Profile") or "")
            role = str(record.get("Demo Role") or "")
            if profile:
                roles_by_profile.setdefault(profile, set()).add(role)

        self.assertEqual(
            set(roles_by_profile),
            {
                "road_civil_infrastructure",
                "parks_landscape",
                "professional_engineering_design",
            },
        )
        for roles in roles_by_profile.values():
            self.assertIn("strong_fit", roles)
            self.assertIn("false_positive", roles)
            self.assertIn("capacity_deadline_warning", roles)

    def test_sample_records_exercise_demo_profile_outcomes(self) -> None:
        solicitations = sample_solicitations()
        awards = sample_awards()

        for profile in _demo_profiles():
            evaluated = evaluate_opportunities(profile, solicitations, awards, date_today())
            by_role = {
                item.solicitation.raw.get("Demo Role"): item
                for item in evaluated
                if item.solicitation.raw.get("Demo Profile") == profile.profile_id
            }

            self.assertNotEqual(by_role["strong_fit"].label, "Skip", profile.profile_id)
            self.assertEqual(by_role["false_positive"].label, "Skip", profile.profile_id)
            self.assertTrue(
                by_role["capacity_deadline_warning"].capacity_assessment.warnings,
                profile.profile_id,
            )

    def test_default_profile_is_road_civil_contractor(self) -> None:
        profile = BusinessProfile()

        self.assertEqual(profile.profile_id, "road_civil_infrastructure")
        self.assertEqual(profile.label, "Road/Civil Infrastructure Contractor")
        self.assertIn("road", profile.business_type)
        self.assertIn("bridge rehabilitation", profile.skills)
        self.assertIn("watermain construction", profile.skills)
        self.assertIn("bonding capacity", profile.ready_documents)
        self.assertIn("pure software implementation", profile.missing_capabilities)
        self.assertEqual(profile.ytd_solicitation_hits, 45)

    def test_offline_fallback_loading(self) -> None:
        with patch.dict(os.environ, {config.OFFLINE_ENV: "1"}, clear=False):
            bundle = load_procurement_data()

        self.assertGreaterEqual(len(bundle.solicitations), 3)
        self.assertGreaterEqual(len(bundle.awards), 2)
        self.assertIn(config.SOLICITATIONS_SOURCE, bundle.source_status)
        self.assertIn("fallback_sample", bundle.source_status[config.SOLICITATIONS_SOURCE])
        self.assertTrue(bundle.warnings)

    def test_cache_source_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            with patch.object(config, "CACHE_DIR", cache_dir):
                with patch("contract_radar.data._fetch_datastore_search") as fetch:
                    fetch.side_effect = [
                        [
                            {
                                "Document Number": "RFQ-CACHE-1",
                                "RFx (Solicitation) Type": "Request for Tender",
                                "High Level Category": "Construction Services",
                                "Solicitation Document Description": "Road repairs, sidewalk repairs, curb repair, and asphalt paving",
                                "Division": "Transportation Services",
                                "Issue Date": "2026-05-01",
                                "Submission Deadline": "2026-06-01",
                            }
                        ],
                        [
                            {
                                "Document Number": "RFQ-AWARD-1",
                                "RFx (Solicitation) Type": "Request for Tender",
                                "High Level Category": "Construction Services",
                                "Successful Supplier": "Local Civil Works",
                                "Award": "$12,500",
                                "Award Authority Obtained Date": "2025-06-01",
                                "Division": "Transportation Services",
                                "Solicitation Document Description": "Road repairs, sidewalk repairs, curb repair, and asphalt paving",
                            }
                        ],
                    ]

                    live_bundle = load_procurement_data(refresh=True)
                    cached_bundle = load_procurement_data(refresh=False)

        self.assertIn("live (1 records)", live_bundle.source_status[config.SOLICITATIONS_SOURCE])
        self.assertIn("cache (1 records)", cached_bundle.source_status[config.SOLICITATIONS_SOURCE])
        self.assertEqual(cached_bundle.solicitations[0].document_number, "RFQ-CACHE-1")
        self.assertEqual(cached_bundle.awards[0].award_value, 12500.0)

    def test_live_failure_uses_sample_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(config, "CACHE_DIR", Path(tmpdir)):
                with patch("contract_radar.data._fetch_datastore_search", side_effect=OSError("network down")):
                    bundle = load_procurement_data(refresh=True)

        self.assertIn("fallback_sample", bundle.source_status[config.SOLICITATIONS_SOURCE])
        self.assertIn("fallback_sample", bundle.source_status[config.AWARDED_CONTRACTS_SOURCE])
        self.assertTrue(any("incomplete" in warning for warning in bundle.warnings))

    @unittest.skipUnless(_cudf_available(), "RAPIDS/cuDF is not installed")
    def test_rapids_prepare_records_preserves_sample_labels(self) -> None:
        warnings: list[str] = []
        prepared_records, rapids_mode = _prepare_records(
            "solicitations",
            SAMPLE_SOLICITATION_RECORDS,
            100,
            warnings,
        )
        profile = BusinessProfile()
        awards = sample_awards()
        python_labels = {
            item.solicitation.document_number: item.label
            for item in evaluate_opportunities(profile, sample_solicitations(), awards, date_today())
        }
        rapids_labels = {
            item.solicitation.document_number: item.label
            for item in evaluate_opportunities(
                profile,
                [Solicitation.from_record(record) for record in prepared_records],
                awards,
                date_today(),
            )
        }

        self.assertEqual(rapids_mode, "rapids_cudf")
        self.assertEqual(python_labels, rapids_labels)


def date_today():
    from datetime import date

    return date(2026, 5, 30)


def _demo_profiles() -> list[BusinessProfile]:
    return [
        BusinessProfile.from_payload(
            {
                "profile_id": "road_civil_infrastructure",
                "name": "Road/Civil Infrastructure Contractor",
                "business_type": "road civil infrastructure asphalt paving curb sidewalk municipal contractor",
                "max_contract_value": 650000,
                "active_pursuit_count": 2,
                "max_active_pursuits": 3,
                "skills": [
                    "road resurfacing",
                    "asphalt paving",
                    "curb repair",
                    "concrete sidewalk replacement",
                    "minor drainage restoration",
                    "traffic control",
                    "pavement markings",
                    "pothole repair",
                    "catch basin frame adjustments",
                    "laneway repair",
                ],
                "missing_capabilities": [
                    "software implementation",
                    "SaaS licensing",
                    "data migration",
                    "professional engineering services",
                    "design drawings",
                    "arborist services",
                    "food supply",
                ],
                "response_days_available": 12,
            }
        ),
        BusinessProfile.from_payload(
            {
                "profile_id": "parks_landscape",
                "name": "Parks/Landscape Contractor",
                "business_type": "parks playground landscaping arborist public realm contractor",
                "max_contract_value": 650000,
                "active_pursuit_count": 1,
                "max_active_pursuits": 3,
                "skills": [
                    "park improvements",
                    "playground surfacing repairs",
                    "trail resurfacing",
                    "planting beds",
                    "topsoil supply",
                    "sod restoration",
                    "site furnishings",
                    "fencing",
                    "arborist services",
                    "tree pruning",
                    "stump grinding",
                    "trail clearing",
                    "sports field turf repairs",
                ],
                "missing_capabilities": [
                    "software implementation",
                    "food supply",
                    "beverages",
                    "road paving",
                    "professional engineering services",
                    "general contractor",
                ],
                "response_days_available": 12,
            }
        ),
        BusinessProfile.from_payload(
            {
                "profile_id": "professional_engineering_design",
                "name": "Professional Engineering/Design Firm",
                "business_type": "professional engineering design planning contract administration firm",
                "max_contract_value": 900000,
                "active_pursuit_count": 2,
                "max_active_pursuits": 4,
                "skills": [
                    "professional engineering services",
                    "preliminary design",
                    "detailed design",
                    "traffic safety review",
                    "public realm accessibility upgrades",
                    "tender support",
                    "construction inspection",
                    "contract administration",
                    "bridge condition assessment",
                    "structural engineering review",
                    "environmental assessment support",
                    "design drawings",
                ],
                "missing_capabilities": [
                    "construction services",
                    "general contractor",
                    "road paving",
                    "asphalt paving",
                    "pavement markings",
                    "traffic control",
                    "equipment labour materials",
                    "food supply",
                    "software implementation",
                ],
                "response_days_available": 14,
            }
        ),
    ]


if __name__ == "__main__":
    unittest.main()
