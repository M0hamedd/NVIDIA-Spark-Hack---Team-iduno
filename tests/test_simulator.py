from __future__ import annotations

import unittest

from contract_radar.simulator import simulate_month


class SimulatorTests(unittest.TestCase):
    def test_empty_scan_creates_scan_and_no_match_events(self) -> None:
        timeline = simulate_month(
            {
                "as_of": "2026-05-30",
                "metrics": {"solicitations_loaded": 12, "awards_loaded": 20},
                "top_opportunities": [],
                "watchlist": [],
                "all_evaluated": [],
            }
        )

        self.assertEqual([event["type"] for event in timeline], ["scan_day", "no_matches"])
        self.assertEqual(timeline[0]["date"], "2026-05-30")
        self.assertIn("Scanned 12 solicitations", timeline[0]["message"])

    def test_timeline_generates_alert_watch_deadline_and_approval_events(self) -> None:
        bid = {
            "label": "Pursue",
            "matched_terms": ["road resurfacing", "asphalt paving", "curb repair"],
            "days_until_deadline": 5,
            "missing_requirements": ["proof of insurance"],
            "solicitation": {
                "document_number": "RFQ-1",
                "description": "Municipal road resurfacing and curb repair",
            },
        }
        watch = {
            "label": "Monitor",
            "matched_terms": ["traffic control"],
            "days_until_deadline": 40,
            "solicitation": {
                "document_number": "RFP-2",
                "description": "Road corridor traffic control services",
            },
        }

        timeline = simulate_month(
            {
                "as_of": "2026-05-30",
                "top_opportunities": [bid],
                "watchlist": [watch],
                "all_evaluated": [bid, watch],
                "metrics": {"solicitations_loaded": 2, "awards_loaded": 4},
            },
            days=30,
        )
        types = [event["type"] for event in timeline]

        self.assertEqual(types.count("scan_day"), 1)
        self.assertEqual(types.count("new_alert"), 1)
        self.assertEqual(types.count("approval_ready"), 1)
        self.assertEqual(types.count("deadline_approaching"), 1)
        self.assertEqual(types.count("watchlist_update"), 1)
        self.assertEqual([event["day"] for event in timeline], sorted(event["day"] for event in timeline))

    def test_next_day_monitor_surfaces_pursue_alert(self) -> None:
        bid = {
            "label": "Pursue",
            "matched_terms": ["park improvements", "trail resurfacing", "planting beds"],
            "days_until_deadline": 12,
            "missing_requirements": [],
            "solicitation": {
                "document_number": "RFQ-PARK-7",
                "description": "Next-day park trail and planting restoration call",
            },
        }

        timeline = simulate_month(
            {
                "as_of": "2026-05-30",
                "top_opportunities": [bid],
                "watchlist": [],
                "all_evaluated": [bid],
                "metrics": {"solicitations_loaded": 1, "awards_loaded": 6},
            },
            days=1,
        )
        alerts = [event for event in timeline if event["type"] == "new_alert"]

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["date"], "2026-05-31")
        self.assertEqual(alerts[0]["label"], "Pursue")
        self.assertIn("Next-day monitor surfaced", alerts[0]["message"])
        self.assertIn("park improvements", alerts[0]["message"])

    def test_next_day_monitor_reports_filtered_false_positive(self) -> None:
        bid = {
            "label": "Review",
            "matched_terms": ["professional engineering services", "detailed design"],
            "days_until_deadline": 6,
            "solicitation": {
                "document_number": "RFP-ENG-1",
                "description": "Bridge condition assessment and detailed design",
            },
        }
        skipped = {
            "label": "Skip",
            "matched_terms": ["contract administration"],
            "rejection_reasons": ["blocked capability mismatch"],
            "missing_requirements": ["general contractor"],
            "solicitation": {
                "document_number": "RFQ-CONSTRUCTION-2",
                "description": "Construction-only asphalt paving delivery",
            },
        }

        timeline = simulate_month(
            {
                "as_of": "2026-05-30",
                "top_opportunities": [],
                "watchlist": [bid],
                "skipped": [skipped],
                "all_evaluated": [bid, skipped],
                "metrics": {"solicitations_loaded": 2, "awards_loaded": 3, "rejected_count": 1},
            },
            days=1,
        )
        filter_events = [event for event in timeline if event["type"] == "false_positive_filter"]

        self.assertEqual(len(filter_events), 1)
        self.assertEqual(filter_events[0]["date"], "2026-05-31")
        self.assertEqual(filter_events[0]["label"], "Skip")
        self.assertIn("poor-fit", filter_events[0]["title"])
        self.assertIn("blocked capability mismatch", filter_events[0]["message"])
        self.assertIn("rejected 1 poor-fit", timeline[0]["message"])


if __name__ == "__main__":
    unittest.main()
