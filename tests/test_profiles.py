from __future__ import annotations

import unittest

from contract_radar.profiles import SUPPORTED_PROFILE_IDS, profile_from_payload, supported_profiles
from contract_radar.service import ContractRadarService


class SupportedProfileTests(unittest.TestCase):
    def test_supported_profiles_are_exposed_in_health(self) -> None:
        service = ContractRadarService()

        health = service.health()

        self.assertEqual(
            [profile["profile_id"] for profile in health["supported_profiles"]],
            list(SUPPORTED_PROFILE_IDS),
        )

    def test_profile_from_payload_selects_requested_supported_profile(self) -> None:
        profile = profile_from_payload({"profile_id": "parks_landscape"})

        self.assertEqual(profile.profile_id, "parks_landscape")
        self.assertEqual(profile.name, "Greenline Parks & Landscape Ltd.")
        self.assertIn("topsoil supply", profile.skills)
        self.assertEqual(profile.ytd_solicitation_hits, 42)

    def test_supported_profiles_cover_three_distinct_vendor_types(self) -> None:
        profiles = supported_profiles()
        business_types = {profile["business_type"] for profile in profiles}

        self.assertEqual(len(profiles), 3)
        self.assertEqual(len(business_types), 3)
        self.assertEqual(profiles[0]["profile_id"], "road_civil_infrastructure")
        self.assertTrue(any("road" in item for item in business_types))
        self.assertTrue(any("landscaping" in item for item in business_types))
        self.assertTrue(any("engineering" in item for item in business_types))
        self.assertTrue(all("lane_basis" in profile for profile in profiles))
        self.assertTrue(all("exclusive_best_fit_hits" in profile for profile in profiles))


if __name__ == "__main__":
    unittest.main()
