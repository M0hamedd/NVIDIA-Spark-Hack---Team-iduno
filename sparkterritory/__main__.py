from __future__ import annotations

import json
import sys

from sparkterritory.service import RecommendationService


def main() -> None:
    payload = {
        "business_type": "window_washing",
        "crew_size": 2,
        "base_neighbourhood": "Scarborough Village",
        "max_travel_minutes": 30,
        "customer_focus": "residential",
    }
    if len(sys.argv) > 1:
        payload["base_neighbourhood"] = sys.argv[1]
    result = RecommendationService().recommend(payload)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
