"""Host-side event API for the sandboxed agent. Wraps the `ssw` CLI (scope section 0.5).

Env: SSW_CMD (default: python3 <this folder>/ssw_fake.py), SSW_API_HOST (127.0.0.1),
SSW_API_PORT (8100).
"""

import json
import math
import os
import re
import shlex
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import stats  # noqa: E402
from alert import build_alert  # noqa: E402

MAX_HOURS = 24 * 31
MAX_AFTER_MIN = 7 * 24 * 60
_escalated: set[int] = set()
_escalated_lock = threading.Lock()

STATUSES = ("new", "posted", "approved", "false_alarm")
DISPOSITIONS = ("approved", "false_alarm")
SLACK_USER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
ID_RE = re.compile(r"^[0-9]{1,18}$")
CLI_TIMEOUT_S = 15


class CliError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def ssw_cmd() -> list[str]:
    raw = os.environ.get("SSW_CMD")
    if raw:
        return shlex.split(raw)
    return [sys.executable or "python3", str(HERE / "ssw_fake.py")]


def run_ssw(*args: str):
    try:
        proc = subprocess.run(
            ssw_cmd() + list(args),
            capture_output=True, text=True, timeout=CLI_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CliError(502, f"cli failed: {type(exc).__name__}")
    stdout = proc.stdout.strip()
    try:
        data = json.loads(stdout) if stdout else None
    except json.JSONDecodeError:
        data = stdout
    if proc.returncode != 0:
        if isinstance(data, dict) and str(data.get("error", "")).replace(" ", "_") == "not_found":
            raise CliError(404, "not found")
        raise CliError(502, f"cli exited {proc.returncode}")
    if isinstance(data, dict) and "error" in data:
        if str(data["error"]).replace(" ", "_") == "not_found":
            raise CliError(404, "not found")
        raise CliError(502, "cli error")
    return data


def events_for(statuses) -> list[dict]:
    out = []
    for status in statuses:
        rows = run_ssw("events", "--status", status)
        if not isinstance(rows, list):
            raise CliError(502, "cli returned no event list")
        out.extend(r for r in rows if isinstance(r, dict))
    return out


def number_param(query: dict, name: str, default: float, low: float, high: float):
    """Parse a numeric query param in [low, high]. Returns None when invalid."""
    raw = query.get(name, [None])[0]
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        return None
    if not math.isfinite(value) or not low <= value <= high:
        return None
    return value


def claim_escalations(events: list[dict]) -> list[dict]:
    """Keep only events not escalated before by this process, and remember them."""
    with _escalated_lock:
        fresh = [ev for ev in events if int(ev["id"]) not in _escalated]
        _escalated.update(int(ev["id"]) for ev in fresh)
    return fresh


class Handler(BaseHTTPRequestHandler):
    server_version = "ssw-api/1"

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.log_date_time_string()} {self.address_string()} {fmt % args}\n")

    def _send(self, status: int, body) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _error(self, status: int, message: str) -> None:
        self._send(status, {"error": message})

    def _parts(self) -> tuple[list[str], dict]:
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        return parts, parse_qs(url.query)

    def _dispatch(self, method: str) -> None:
        try:
            parts, query = self._parts()
            status, body = self._route(method, parts, query)
            self._send(status, body)
        except CliError as exc:
            self._error(exc.status, exc.message)
        except Exception as exc:  # last resort: never leak a traceback to the client
            sys.stderr.write(f"internal error: {exc!r}\n")
            self._error(500, "internal error")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length <= 0 or length > 65536:
            return None
        try:
            return json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _route(self, method: str, parts: list[str], query: dict):
        if method == "GET" and parts == ["health"]:
            return 200, {"ok": True}

        if method == "GET" and parts == ["pending"]:
            data = run_ssw("pending")
            text = data if isinstance(data, str) else json.dumps(data)
            return 200, {"text": text or "NO_REPLY"}

        if method == "GET" and parts in (["stats"], ["digest"]):
            hours = number_param(query, "hours", 24, 0.01, MAX_HOURS)
            if hours is None:
                return 400, {"error": "bad hours"}
            start, end = stats.window(datetime.now(timezone.utc), hours)
            result = stats.compute_stats(events_for(STATUSES), start, end)
            if parts == ["stats"]:
                return 200, result
            return 200, {"text": stats.digest_text(result)}

        if method == "GET" and parts == ["escalations"]:
            after_min = number_param(query, "after_min", 10, 0, MAX_AFTER_MIN)
            if after_min is None:
                return 400, {"error": "bad after_min"}
            now = datetime.now(timezone.utc)
            due = claim_escalations(stats.escalations(events_for(["posted"]), now, after_min))
            if not due:
                return 200, {"text": "NO_REPLY"}
            lines = [stats.escalation_text(ev, stats.minutes_waiting(ev, now)) for ev in due]
            return 200, {"text": "\n".join(lines), "event_ids": [int(ev["id"]) for ev in due]}

        if method == "GET" and parts == ["events"]:
            status = query.get("status", ["new"])[0]
            if status not in STATUSES:
                return 400, {"error": "bad status"}
            return 200, run_ssw("events", "--status", status)

        if len(parts) >= 2 and parts[0] == "events":
            event_id = parts[1]
            if not ID_RE.match(event_id):
                return 400, {"error": "bad id"}
            rest = parts[2:]
            if method == "GET" and rest == []:
                return 200, run_ssw("event", event_id)
            if method == "GET" and rest == ["alert"]:
                return 200, build_alert(run_ssw("event", event_id))
            if method == "POST" and rest == ["posted"]:
                return 200, run_ssw("mark-posted", event_id)
            if method == "POST" and rest == ["disposition"]:
                body = self._read_json()
                if not isinstance(body, dict):
                    return 400, {"error": "bad json body"}
                disposition = body.get("disposition")
                by = body.get("by")
                if disposition not in DISPOSITIONS:
                    return 400, {"error": "bad disposition"}
                if not isinstance(by, str) or not SLACK_USER_RE.match(by):
                    return 400, {"error": "bad by"}
                return 200, run_ssw("dispose", event_id, disposition, "--by", by)

        return 404, {"error": "no such route"}


def make_server(host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    host = os.environ.get("SSW_API_HOST", "127.0.0.1")
    port = int(os.environ.get("SSW_API_PORT", "8100"))
    server = make_server(host, port)
    sys.stderr.write(f"ssw-api listening on {host}:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
