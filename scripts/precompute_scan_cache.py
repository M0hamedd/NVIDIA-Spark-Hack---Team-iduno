from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Precompute scan results that app.py can replay instantly during demos."
    )
    parser.add_argument("--offline", action="store_true", help="Use cached Toronto Open Data without live refresh.")
    parser.add_argument("--refresh", action="store_true", help="Refresh Toronto Open Data before precomputing.")
    parser.add_argument("--profile", default="", help="Supported business profile id. Defaults to all profiles.")
    parser.add_argument("--priority-mode", default="best_win_chance", help="Priority mode for the precomputed scan.")
    parser.add_argument("--as-of", default="", help="ISO date for the scan. Defaults to today.")
    parser.add_argument(
        "--without-nemotron",
        action="store_true",
        help="Disable Nemotron while precomputing. Omit on Spark to cache custom local Nemotron briefs.",
    )
    args = parser.parse_args()

    if args.offline:
        os.environ["CONTRACT_RADAR_OFFLINE"] = "1"
    if args.without_nemotron:
        os.environ["CONTRACT_RADAR_DISABLE_NEMOTRON"] = "1"
    os.environ.pop("CONTRACT_RADAR_USE_PRECOMPUTED_SCAN", None)

    from contract_radar.matcher import normalize_priority_mode
    from contract_radar.precomputed import write_precomputed_scan
    from contract_radar.profiles import supported_profiles
    from contract_radar.service import ContractRadarService

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    priority_mode = normalize_priority_mode(args.priority_mode)
    profiles = _profiles_to_precompute(args.profile, supported_profiles())
    service = ContractRadarService()
    written: list[Path] = []

    for index, profile in enumerate(profiles):
        payload: dict[str, Any] = {
            "profile_id": profile["profile_id"],
            "priority_mode": priority_mode,
            "as_of": as_of.isoformat(),
            "refresh": bool(args.refresh and index == 0),
        }
        scan = service.scan(payload)
        written.extend(
            write_precomputed_scan(
                scan_result=scan,
                profile_id=str(profile["profile_id"]),
                priority_mode=priority_mode,
                as_of=as_of,
            )
        )
        metrics = scan.get("metrics") or {}
        print(
            f"{profile['profile_id']}: runtime={metrics.get('runtime_ms')} ms, "
            f"NIM={metrics.get('nemotron_mode')}, briefs={metrics.get('briefs_generated')}"
        )

    for path in written:
        print(f"wrote {path}")
    return 0


def _profiles_to_precompute(profile_id: str, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not profile_id:
        return profiles
    matches = [profile for profile in profiles if profile.get("profile_id") == profile_id]
    if not matches:
        known = ", ".join(str(profile.get("profile_id")) for profile in profiles)
        raise SystemExit(f"Unknown profile_id {profile_id!r}. Known profiles: {known}")
    return matches


if __name__ == "__main__":
    raise SystemExit(main())
