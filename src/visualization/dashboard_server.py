"""Web server for the EdgeSwarm Fleet Command Center.

Serves:
  /                  -> redirects to /command-center
  /command-center    -> the 3D Fleet Command Center (command_center.html)
  /static/...        -> local assets (three.js, fonts, 3D twin module); works offline
  /api/swarm/state | catalog | benchmark   (GET)
  /api/swarm/command                        (POST)

The older "classic" dashboard and its API were removed. The legacy baseline simulator is still available from the
CLI (`python main.py --mode demo / benchmark`).
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

ROOT = Path(__file__).resolve().parent
STATIC = (ROOT / "static").resolve()
CONTENT_TYPES = {".js": "application/javascript; charset=utf-8", ".mjs": "application/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".json": "application/json", ".woff2": "font/woff2",
                 ".png": "image/png", ".svg": "image/svg+xml", ".txt": "text/plain; charset=utf-8"}


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "EdgeSwarm/1.0"

    def log_message(self, fmt, *args):  # keep the console quiet
        return

    def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("", "/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/command-center")
            self.end_headers()
            return
        if path.rstrip("/") == "/command-center":
            self._send(200, (ROOT / "command_center.html").read_bytes(), "text/html; charset=utf-8")
            return
        if path.startswith("/api/swarm/"):
            from src.command_center.controller import get_controller
            ctl = get_controller()
            routes = {"/api/swarm/state": ctl.state, "/api/swarm/catalog": ctl.catalog, "/api/swarm/benchmark": ctl.benchmark}
            fn = routes.get(path)
            if fn is not None:
                self._send_json(fn())
                return
        if path.startswith("/static/"):
            f = (STATIC / path[len("/static/"):]).resolve()
            if f.is_file() and str(f).startswith(str(STATIC)):
                self._send(200, f.read_bytes(), CONTENT_TYPES.get(f.suffix, "application/octet-stream"), "public, max-age=3600")
                return
        self._send(404, b"Not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path.startswith("/api/swarm/command"):
            n = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads((self.rfile.read(n) if n > 0 else b"{}").decode("utf-8"))
            except Exception:
                data = {}
            from src.command_center.controller import get_controller
            try:
                res = get_controller().command(data)
                code = 200 if res.get("ok") else 400
            except Exception as exc:  # report errors to the UI instead of dropping the connection
                res, code = {"ok": False, "error": str(exc)}, 500
            self._send_json(res, code)
            return
        self._send(404, b"Not found", "text/plain; charset=utf-8")


def start_dashboard(host: str = "127.0.0.1", port: int = 8000):
    server = None
    for candidate in range(port, port + 20):
        try:
            server = ThreadingHTTPServer((host, candidate), DashboardHandler)
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError(f"No free port found starting from {port}")
    print(f"EdgeSwarm Fleet Command Center: http://{host}:{server.server_address[1]}/command-center", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    start_dashboard(a.host, a.port)
