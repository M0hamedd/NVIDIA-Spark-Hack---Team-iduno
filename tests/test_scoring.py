from __future__ import annotations

import unittest

from sparkterritory.data import DataSignals
from sparkterritory.samples import (
    SAMPLE_CURRENT_BY_DISTRICT,
    SAMPLE_FUTURE_BY_DISTRICT,
    SAMPLE_GROWTH_BY_DISTRICT,
    SAMPLE_NEIGHBOURHOODS,
)
from sparkterritory.scoring import BusinessProfile, score_neighbourhoods, split_recommendations


class ScoringTests(unittest.TestCase):
    def sample_signals(self) -> DataSignals:
        return DataSignals(
            neighbourhoods=SAMPLE_NEIGHBOURHOODS,
            current_by_district=SAMPLE_CURRENT_BY_DISTRICT,
            growth_by_district=SAMPLE_GROWTH_BY_DISTRICT,
            future_by_district=SAMPLE_FUTURE_BY_DISTRICT,
            source_status={"sample": "embedded_fallback"},
            warnings=[],
        )

    def test_scores_are_normalized(self) -> None:
        scored = score_neighbourhoods(BusinessProfile(), self.sample_signals())
        self.assertGreaterEqual(len(scored), 5)
        for item in scored:
            for key in (
                "overall_score",
                "current_demand_score",
                "future_growth_score",
                "customer_fit_score",
                "growth_momentum_score",
                "operational_feasibility_score",
            ):
                self.assertGreaterEqual(item[key], 0)
                self.assertLessEqual(item[key], 100)

    def test_overall_score_uses_documented_weights(self) -> None:
        scored = score_neighbourhoods(BusinessProfile(), self.sample_signals())
        item = scored[0]
        expected = round(
            item["current_demand_score"] * 0.35
            + item["future_growth_score"] * 0.25
            + item["customer_fit_score"] * 0.20
            + item["growth_momentum_score"] * 0.10
            + item["operational_feasibility_score"] * 0.10
        )
        self.assertEqual(item["overall_score"], expected)

    def test_recommendations_have_evidence(self) -> None:
        scored = score_neighbourhoods(BusinessProfile(), self.sample_signals())
        target_now, future = split_recommendations(scored)
        self.assertEqual(len(target_now), 5)
        self.assertEqual(len(future), 3)
        self.assertGreaterEqual(len(target_now[0]["evidence"]), 3)
        self.assertTrue(any(item["future_growth_score"] > 0 for item in scored))

    def test_base_location_changes_operational_scores(self) -> None:
        scarborough = score_neighbourhoods(BusinessProfile(base_neighbourhood="Scarborough Village"), self.sample_signals())
        etobicoke = score_neighbourhoods(BusinessProfile(base_neighbourhood="Mimico (includes Humber Bay Shores)"), self.sample_signals())
        scarborough_lookup = {item["name"]: item for item in scarborough}
        etobicoke_lookup = {item["name"]: item for item in etobicoke}
        self.assertNotEqual(
            scarborough_lookup["Scarborough Village"]["operational_feasibility_score"],
            etobicoke_lookup["Scarborough Village"]["operational_feasibility_score"],
        )


if __name__ == "__main__":
    unittest.main()
