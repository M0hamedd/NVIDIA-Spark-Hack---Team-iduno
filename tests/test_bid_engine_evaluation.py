from __future__ import annotations

import unittest
from datetime import date

from contract_radar.profiles import SUPPORTED_PROFILE_IDS
from scripts.evaluate_bid_engine import evaluate_bid_engine


class BidEngineEvaluationTests(unittest.TestCase):
    def test_offline_evaluation_returns_all_supported_profiles(self) -> None:
        summary = evaluate_bid_engine("all", offline=True, as_of=date(2026, 5, 30))

        profile_ids = [item["profile_id"] for item in summary["profiles"]]

        self.assertEqual(profile_ids, list(SUPPORTED_PROFILE_IDS))
        self.assertIn("Toronto Bids Solicitations=cache_offline", summary["data_mode"])
        self.assertGreater(summary["solicitations_evaluated"], 100)
        self.assertGreater(summary["awards_loaded"], 100)

    def test_bid_engine_shortlist_reduces_naive_keywords_and_skips_false_positives(self) -> None:
        summary = evaluate_bid_engine("all", offline=True, as_of=date(2026, 5, 30))

        for profile in summary["profiles"]:
            with self.subTest(profile=profile["profile_id"]):
                self.assertLessEqual(
                    profile["bid_engine_actionable_count"],
                    profile["naive_keyword_candidate_count"],
                )
                self.assertGreater(profile["skipped_false_positives"], 0)
                self.assertGreater(profile["shortlist_reduction_ratio"], 0)
                self.assertGreater(profile["estimated_review_hours_saved"], 0)
                self.assertIsNotNone(profile["top_opportunity"])
                self.assertTrue(profile["top_opportunity"]["document_number"])
                self.assertTrue(profile["top_opportunity"]["title"])
                self.assertTrue(profile["best_current_opportunity"]["document_number"])
                self.assertTrue(profile["buyer_division_pattern"])
                self.assertTrue(profile["similar_award_range"])
                self.assertGreater(profile["similar_awards_grounded"], 0)
                self.assertGreater(len(profile["similar_award_examples"]), 0)
                self.assertGreater(len(profile["false_positive_categories"]), 0)


if __name__ == "__main__":
    unittest.main()
