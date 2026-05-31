from __future__ import annotations

import json
import subprocess
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from contract_radar.matcher import evaluate_opportunities
from contract_radar.models import AwardRecord, Solicitation
from contract_radar.profiles import get_supported_profile
from contract_radar.ranker import (
    build_historical_award_examples,
    build_market_award_examples,
    extract_ranker_features,
    require_sklearn,
)


ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 5, 30)


class RankerTests(unittest.TestCase):
    def test_feature_extraction_distinguishes_fit_false_positive_and_capacity_review(self) -> None:
        profile = get_supported_profile("road_civil_infrastructure")
        awards = [_award()]
        fit = _solicitation(
            "FIT-ROAD",
            "Road repairs sidewalk repairs curb repair asphalt paving and traffic staging.",
            deadline=date(2026, 6, 20),
        )
        false_positive = _solicitation(
            "IT-ROAD",
            "Software implementation, licensing, data migration, and training for road asset reporting.",
            category="Professional Services",
            division="Technology Services",
            deadline=date(2026, 6, 20),
        )
        overloaded = get_supported_profile("road_civil_infrastructure")
        overloaded.active_pursuit_count = overloaded.max_active_pursuits
        urgent = _solicitation(
            "URGENT-ROAD",
            "Road repairs sidewalk repairs curb repair asphalt paving and traffic staging.",
            deadline=date(2026, 6, 2),
        )

        fit_item = evaluate_opportunities(profile, [fit], awards, TODAY)[0]
        false_item = evaluate_opportunities(profile, [false_positive], awards, TODAY)[0]
        review_item = evaluate_opportunities(overloaded, [urgent], awards, TODAY)[0]
        fit_features = extract_ranker_features(profile, fit_item)
        false_features = extract_ranker_features(profile, false_item)
        review_features = extract_ranker_features(overloaded, review_item)

        self.assertEqual(fit_item.label, "Pursue")
        self.assertEqual(false_item.label, "Skip")
        self.assertEqual(review_item.label, "Review")
        self.assertGreater(fit_features["matched_term_count"], false_features["matched_term_count"])
        self.assertGreater(false_features["rejection_reason_count"], 0)
        self.assertEqual(review_features["pursuit_load_overloaded"], 1.0)
        self.assertEqual(review_features["recommended_pursue_after_review"], 1.0)

    def test_ranker_examples_mark_targets_and_hard_negatives(self) -> None:
        profile = get_supported_profile("parks_landscape")
        awards = [
            AwardRecord(
                document_number="AWD-PARK",
                solicitation_type="Request for Tender",
                category="Construction Services",
                supplier="Parks Co",
                award_value=250000,
                award_date=TODAY,
                division="Parks, Forestry & Recreation",
                description="Park improvements, playground installation, planting, trail repairs, and site furnishings.",
            ),
            AwardRecord(
                document_number="AWD-SOFTWARE",
                solicitation_type="Request for Proposal",
                category="Professional Services",
                supplier="Software Co",
                award_value=150000,
                award_date=TODAY,
                division="Technology Services",
                description="Software implementation and data migration for parks reporting.",
            ),
        ]

        examples = build_historical_award_examples(profile, awards, negative_ratio=1)
        positives = [example for example in examples if example.target == 1]
        hard_negatives = [example for example in examples if example.hard_negative]

        self.assertTrue(positives)
        self.assertTrue(hard_negatives)
        self.assertTrue(all(example.document_number.startswith("AWARD:") for example in examples))

    def test_market_award_examples_use_prior_supplier_history_only(self) -> None:
        profile = get_supported_profile("parks_landscape")
        awards = [
            AwardRecord(
                document_number="AWD-PARK-1",
                solicitation_type="Request for Tender",
                category="Construction Services",
                supplier="Parks Co",
                award_value=250000,
                award_date=date(2024, 1, 15),
                division="Parks, Forestry & Recreation",
                description="Park improvements, playground installation, planting, trail repairs, and site furnishings.",
            ),
            AwardRecord(
                document_number="AWD-PARK-2",
                solicitation_type="Request for Tender",
                category="Construction Services",
                supplier="Parks Co",
                award_value=280000,
                award_date=date(2024, 3, 15),
                division="Parks, Forestry & Recreation",
                description="Park improvements, playground installation, planting, trail repairs, and site furnishings.",
            ),
            AwardRecord(
                document_number="AWD-ROAD-1",
                solicitation_type="Request for Tender",
                category="Construction Services",
                supplier="Road Co",
                award_value=900000,
                award_date=date(2024, 4, 15),
                division="Transportation Services",
                description="Road reconstruction, sewer rehabilitation, asphalt paving, and traffic staging.",
            ),
        ]

        examples = build_market_award_examples(profile, awards, negative_ratio=1)
        first = next(example for example in examples if example.document_number == "AWARD:AWD-PARK-1")
        second = next(example for example in examples if example.document_number == "AWARD:AWD-PARK-2")

        self.assertEqual(first.target, 1)
        self.assertEqual(second.target, 1)
        self.assertEqual(first.features["prior_supplier_profile_fit_log"], 0.0)
        self.assertGreater(second.features["prior_supplier_profile_fit_log"], 0.0)
        self.assertGreater(second.features["prior_segment_awards_log"], 0.0)

    def test_require_sklearn_has_clear_install_message_when_missing(self) -> None:
        real_import = __import__

        def fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "sklearn":
                raise ImportError("no sklearn")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaisesRegex(RuntimeError, "python -m pip install -r requirements.txt"):
                require_sklearn()

    def test_train_bid_ranker_script_returns_stable_json_metrics(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "train_bid_ranker.py"),
                "--offline",
                "--profiles",
                "all",
                "--json",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        payload = json.loads(completed.stdout)

        self.assertGreater(payload["examples"], 1000)
        self.assertGreater(payload["historical_award_examples"], 0)
        self.assertGreater(payload["positive_examples"], 0)
        self.assertIn("precision_at_3", payload)
        self.assertIn("recall_at_5", payload)
        self.assertIn("false_positive_rate_top_5", payload)
        self.assertIn("top_weighted_features", payload)
        self.assertIn("naive_baseline", payload)
        self.assertGreater(payload["naive_baseline"]["skipped_false_positives"], 0)
        self.assertEqual(payload["award_history_model"]["status"], "trained")
        self.assertIn("precision_at_10", payload["award_history_model"])
        self.assertIn("top_decile_lift", payload["award_history_model"])
        self.assertIn("supplier_intelligence", payload["award_history_model"])


def _solicitation(
    document_number: str,
    description: str,
    category: str = "Construction Services",
    division: str = "Transportation Services",
    deadline: date | None = None,
) -> Solicitation:
    return Solicitation(
        document_number=document_number,
        solicitation_type="Request for Tender",
        category=category,
        description=description,
        division=division,
        issue_date=TODAY,
        submission_deadline=deadline,
    )


def _award() -> AwardRecord:
    return AwardRecord(
        document_number="AWD-ROAD",
        solicitation_type="Request for Tender",
        category="Construction Services",
        supplier="Road Co",
        award_value=650000,
        award_date=TODAY,
        division="Transportation Services",
        description="Road repairs, sidewalk repairs, curb repair, asphalt paving, and traffic staging.",
    )


if __name__ == "__main__":
    unittest.main()
