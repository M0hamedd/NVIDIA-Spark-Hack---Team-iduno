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
        self.assertEqual(solicitations[0].document_number, "RFQ-2026-1001")
        self.assertIn("building automation", solicitations[0].description.lower())
        self.assertIn("hvac", solicitations[0].description.lower())
        self.assertGreater(awards[0].award_value, 0)

    def test_default_profile_is_hvac_controls_contractor(self) -> None:
        profile = BusinessProfile()

        self.assertEqual(profile.name, "GTA Mechanical & Controls Ltd.")
        self.assertIn("HVAC", profile.business_type)
        self.assertIn("building automation systems/BAS controls", profile.skills)
        self.assertIn("boiler service", profile.skills)
        self.assertIn("chiller service", profile.skills)
        self.assertIn("technician certifications", profile.ready_documents)
        self.assertIn("major design/build construction", profile.missing_capabilities)

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
                                "RFx (Solicitation) Type": "Request for Quotation",
                                "High Level Category": "Goods and Services",
                                "Solicitation Document Description": "HVAC maintenance and BAS controls support",
                                "Division": "Facilities",
                                "Issue Date": "2026-05-01",
                                "Submission Deadline": "2026-06-01",
                            }
                        ],
                        [
                            {
                                "Document Number": "RFQ-AWARD-1",
                                "RFx (Solicitation) Type": "Request for Quotation",
                                "High Level Category": "Goods and Services",
                                "Successful Supplier": "Local HVAC Controls",
                                "Award": "$12,500",
                                "Award Authority Obtained Date": "2025-06-01",
                                "Division": "Facilities",
                                "Solicitation Document Description": "HVAC maintenance and BAS controls support",
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


if __name__ == "__main__":
    unittest.main()
