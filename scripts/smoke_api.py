from __future__ import annotations

import argparse
import json
import sys
from typing import Any
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:8080"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke-test a running Live Contract Radar API. Start the app first with "
            "`python app.py`, then run this command."
        )
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base URL. Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--timeout", type=float, default=20.0, help="Request timeout in seconds. Default: 20")
    parser.add_argument("--days", type=int, default=7, help="Simulation window for /api/simulate. Default: 7")
    parser.add_argument("--refresh", action="store_true", help="Ask /api/scan to refresh live Toronto data.")
    parser.add_argument("--json", action="store_true", help="Print compact JSON result details.")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    smoke = SmokeClient(base_url=base_url, timeout=args.timeout)

    try:
        health = smoke.get("/api/health")
        require(health.get("status") == "ok", "/api/health did not return status=ok")
        require("/api/scan" in health.get("endpoints", []), "/api/health did not advertise /api/scan")
        ok("GET /api/health", _health_summary(health))

        scan_payload = {"refresh": bool(args.refresh)}
        if not args.refresh:
            scan_payload["profile_id"] = "road_civil_infrastructure"
        scan = smoke.post("/api/scan", scan_payload)
        require(scan.get("business_profile"), "/api/scan missing business_profile")
        require(scan.get("metrics"), "/api/scan missing metrics")
        require(isinstance(scan.get("all_evaluated"), list), "/api/scan missing all_evaluated list")
        require_real_toronto_sources(scan)
        ok("POST /api/scan", _scan_summary(scan))

        simulate_payload = dict(scan_payload)
        simulate_payload["days"] = args.days
        simulate = smoke.post("/api/simulate", simulate_payload)
        require(isinstance(simulate.get("timeline"), list), "/api/simulate missing timeline list")
        require(simulate.get("metrics"), "/api/simulate missing metrics")
        ok("POST /api/simulate", f"{len(simulate.get('timeline') or [])} timeline events")

        opportunity_id = first_opportunity_id(scan)
        approve_result: dict[str, Any] | None = None
        if opportunity_id:
            approve = smoke.post("/api/approve", {"approved": True, "opportunity_id": opportunity_id})
            packet = approve.get("packet") or {}
            require(approve.get("approved") is True, "/api/approve did not echo approved=true")
            require(packet.get("opportunity_id"), "/api/approve missing packet opportunity_id")
            approve_result = {"opportunity_id": packet.get("opportunity_id")}
            ok("POST /api/approve", f"packet for {packet.get('opportunity_id')}")
        else:
            ok("POST /api/approve", "skipped because scan returned no non-skipped opportunity")

        if args.json:
            print(
                json.dumps(
                    {
                        "base_url": base_url,
                        "health": {
                            "status": health.get("status"),
                            "gpu": health.get("gpu"),
                            "nemotron": health.get("nemotron"),
                        },
                        "scan": {
                            "profile": (scan.get("business_profile") or {}).get("name"),
                            "metrics": scan.get("metrics"),
                        },
                        "simulate": {"timeline_events": len(simulate.get("timeline") or [])},
                        "approve": approve_result or {"skipped": "no non-skipped opportunity"},
                    },
                    indent=2,
                )
            )
    except SmokeFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except (error.HTTPError, error.URLError, TimeoutError, OSError) as exc:
        print(f"FAIL: could not reach {base_url}: {exc}", file=sys.stderr)
        print("Start the app with `python app.py` and retry.", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"FAIL: response was not JSON: {exc}", file=sys.stderr)
        return 1

    print("PASS: API smoke test completed")
    return 0


class SmokeFailure(RuntimeError):
    pass


class SmokeClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url
        self.timeout = timeout

    def get(self, path: str) -> dict[str, Any]:
        with request.urlopen(f"{self.base_url}{path}", timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def require_real_toronto_sources(scan: dict[str, Any]) -> None:
    metrics = scan.get("metrics") or {}
    data_sources = metrics.get("data_sources") or {}
    joined_sources = " ".join(str(value) for value in data_sources.values())
    require("dev_sample_only" not in joined_sources, "/api/scan used bundled dev sample data")
    for bucket in ("top_opportunities", "watchlist", "skipped", "all_evaluated"):
        for item in scan.get(bucket) or []:
            solicitation = item.get("solicitation") or {}
            source_links = solicitation.get("source_links") or {}
            document_number = str(solicitation.get("document_number") or "").strip()
            require(document_number, f"{bucket} item missing document number")
            require(
                source_links.get("is_demo_record") is False,
                f"{bucket} item {document_number} is a bundled demo fixture",
            )
            require(
                bool(source_links.get("open_data_record_url")),
                f"{bucket} item {document_number} missing Toronto Open Data verification link",
            )


def ok(step: str, detail: str) -> None:
    print(f"OK: {step} - {detail}")


def _health_summary(health: dict[str, Any]) -> str:
    gpu = health.get("gpu") or {}
    active_tools = health.get("active_nvidia_tools") or []
    active = ", ".join(active_tools) if active_tools else "fallback"
    return (
        f"nvidia={active}, "
        f"rapids={health.get('rapids_mode') or gpu.get('rapids_mode', 'unknown')}, "
        f"nim={health.get('nim_mode', 'unknown')}"
    )


def _scan_summary(scan: dict[str, Any]) -> str:
    profile = scan.get("business_profile") or {}
    metrics = scan.get("metrics") or {}
    return (
        f"profile={profile.get('name')}, "
        f"evaluated={metrics.get('opportunities_evaluated')}, "
        f"top={len(scan.get('top_opportunities') or [])}, "
        f"skipped={len(scan.get('skipped') or [])}, "
        f"nemotron_mode={metrics.get('nemotron_mode')}"
    )


def first_opportunity_id(scan: dict[str, Any]) -> str:
    for bucket in ("top_opportunities", "watchlist"):
        for item in scan.get(bucket) or []:
            if item.get("label") == "Skip":
                continue
            solicitation = item.get("solicitation") or {}
            document_number = str(solicitation.get("document_number") or "").strip()
            if document_number:
                return document_number
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
