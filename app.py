from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from contract_radar.service import ContractRadarService


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8080"))

service = ContractRadarService()


class ContractRadarHandler(BaseHTTPRequestHandler):
    server_version = "SoBid/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file(STATIC_DIR / "index.html")
            return
        if parsed.path == "/api/health":
            self._send_json(service.health())
            return
        if parsed.path.startswith("/static/"):
            self._send_file(STATIC_DIR / parsed.path.removeprefix("/static/"))
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        routes = {
            "/api/scan": service.scan,
            "/api/simulate": service.simulate,
            "/api/approve": service.approve,
        }
        handler = routes.get(parsed.path)
        if handler is None:
            self._send_json({"error": "Not found"}, status=404)
            return
        try:
            payload = self._read_json()
            self._send_json(handler(payload))
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), format % args))

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8") or "{}")

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "Not found"}, status=404)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    args = _parse_args()
    nemotron_process = None
    use_nemotron = not args.without_nemotron or args.nemotron_setup_only
    if args.without_nemotron and not args.nemotron_setup_only:
        os.environ["CONTRACT_RADAR_DISABLE_NEMOTRON"] = "1"
    if use_nemotron:
        from contract_radar.nemotron_runtime import (
            NemotronRuntimeError,
            ensure_local_nemotron,
            stop_managed_nemotron,
        )

        try:
            nemotron_process = ensure_local_nemotron(setup_only=args.nemotron_setup_only)
        except (NemotronRuntimeError, subprocess.CalledProcessError) as exc:
            print(f"Nemotron startup failed: {exc}", file=sys.stderr)
            print(
                "Start without Nemotron using `python3 app.py --without-nemotron`, "
                "or retry after fixing the setup issue.",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc

        if args.nemotron_setup_only:
            return

    server = ThreadingHTTPServer((HOST, PORT), ContractRadarHandler)
    print(f"SoBid running at http://{HOST}:{PORT}")
    if use_nemotron:
        print(f"Nemotron base URL: {os.environ.get('NIM_BASE_URL')}")
    else:
        print("Nemotron disabled for this run.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping SoBid.")
    finally:
        server.server_close()
        if use_nemotron:
            stop_managed_nemotron(nemotron_process)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SoBid web app.")
    parser.add_argument(
        "--without-nemotron",
        action="store_true",
        help="Skip managed local Nemotron startup and use deterministic extraction fallback.",
    )
    parser.add_argument(
        "--nemotron-setup-only",
        action="store_true",
        help="Build/download the local Nemotron runtime, then exit without starting the app.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
