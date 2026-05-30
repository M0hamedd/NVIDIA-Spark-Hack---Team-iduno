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
            "matched_terms": ["HVAC maintenance", "BAS controls", "preventative maintenance"],
            "days_until_deadline": 5,
            "missing_requirements": ["proof of insurance"],
            "solicitation": {
                "document_number": "RFQ-1",
                "description": "Municipal HVAC and building automation maintenance",
            },
        }
        watch = {
            "label": "Monitor",
            "matched_terms": ["mechanical repair"],
            "days_until_deadline": 40,
            "solicitation": {
                "document_number": "RFP-2",
                "description": "Public facility mechanical repair services",
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
            "matched_terms": ["HVAC service", "chiller maintenance", "municipal facility"],
            "days_until_deadline": 12,
            "missing_requirements": [],
            "solicitation": {
                "document_number": "RFQ-HVAC-7",
                "description": "Next-day HVAC service and controls call",
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
        self.assertIn("HVAC service", alerts[0]["message"])


if __name__ == "__main__":
    unittest.main()
