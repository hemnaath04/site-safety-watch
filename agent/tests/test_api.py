import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(API_DIR))
from alert import build_alert  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ServerCase(unittest.TestCase):
    """Starts the API on a free port with a temp fake DB. Subclasses may set seed_events()."""

    def seed_events(self):
        return None

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.port = free_port()
        db = Path(self.tmp.name) / "ssw.json"
        seeded = self.seed_events()
        if seeded is not None:
            db.write_text(json.dumps(seeded))
        env = dict(os.environ)
        env.pop("SSW_CMD", None)
        env.update({
            "SSW_FAKE_DB": str(db),
            "SSW_API_HOST": "127.0.0.1",
            "SSW_API_PORT": str(self.port),
        })
        self.env = env
        self.proc = subprocess.Popen(
            [sys.executable, str(API_DIR / "server.py")],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                if self.req("GET", "/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            self.fail("server did not start")

    def tearDown(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)
        self.proc.stderr.close()
        self.tmp.cleanup()

    def req(self, method, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method=method)
        if data is not None:
            r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


class ApiTest(ServerCase):
    def test_health(self):
        self.assertEqual(self.req("GET", "/health"), (200, {"ok": True}))

    def test_events_by_status(self):
        code, body = self.req("GET", "/events?status=new")
        self.assertEqual(code, 200)
        self.assertEqual([e["id"] for e in body], [1])
        self.assertEqual(body[0]["zone"], "exit_a")
        self.assertEqual(
            set(body[0]),
            {"id", "ts", "clip", "hazard", "zone", "confidence", "explanation",
             "frame_path", "dedup_key", "status", "disposition_by", "disposition_ts"},
        )
        self.assertEqual([e["id"] for e in self.req("GET", "/events?status=posted")[1]], [2])
        self.assertEqual([e["id"] for e in self.req("GET", "/events?status=approved")[1]], [3])
        self.assertEqual(self.req("GET", "/events?status=bogus")[0], 400)

    def test_event_has_rule_and_fix(self):
        code, ev = self.req("GET", "/events/1")
        self.assertEqual(code, 200)
        self.assertIn("29 CFR 1910.37", ev["rule"])
        self.assertEqual(ev["fix"], "Move the obstruction out of the exit route and tag the zone.")

    def test_bad_and_unknown_ids(self):
        self.assertEqual(self.req("GET", "/events/abc")[0], 400)
        self.assertEqual(self.req("GET", "/events/-1")[0], 400)
        self.assertEqual(self.req("GET", "/events/999")[0], 404)
        self.assertEqual(self.req("GET", "/events/999/alert")[0], 404)
        self.assertEqual(self.req("POST", "/events/999/posted")[0], 404)
        self.assertEqual(self.req("GET", "/nope")[0], 404)

    def test_alert(self):
        code, alert = self.req("GET", "/events/1/alert")
        self.assertEqual(code, 200)
        self.assertEqual(alert["event_id"], 1)
        self.assertEqual(alert["image_path"], "data/frames/event_1.jpg")
        lines = alert["text"].splitlines()
        self.assertIn("Exit route blocked", lines[0])
        self.assertIn("Zone: exit_a", alert["text"])
        self.assertIn("Confidence: 91%", alert["text"])
        self.assertIn("29 CFR 1910.37", alert["text"])
        self.assertIn("Exit routes must be free and unobstructed.", alert["text"])
        self.assertIn("Move the obstruction out of the exit route and tag the zone.", alert["text"])
        self.assertEqual(lines[-1], "Reply `approve 1` or `false-alarm 1`.")
        self.assertNotIn("\u2014", alert["text"])

    def test_mark_posted_then_pending(self):
        code, body = self.req("GET", "/pending")
        self.assertEqual(code, 200)
        self.assertIn("#1", body["text"])
        self.assertNotEqual(body["text"], "NO_REPLY")
        code, ev = self.req("POST", "/events/1/posted")
        self.assertEqual((code, ev["status"]), (200, "posted"))
        self.assertEqual(self.req("GET", "/pending"), (200, {"text": "NO_REPLY"}))
        self.assertEqual(self.req("GET", "/events?status=new"), (200, []))

    def test_disposition(self):
        code, ev = self.req("POST", "/events/2/disposition", {"disposition": "approved", "by": "U123ABC"})
        self.assertEqual(code, 200)
        self.assertEqual(ev["status"], "approved")
        self.assertEqual(ev["disposition_by"], "U123ABC")
        self.assertTrue(ev["disposition_ts"])
        code, ev = self.req("POST", "/events/1/disposition", {"disposition": "false_alarm", "by": "U9"})
        self.assertEqual((code, ev["status"]), (200, "false_alarm"))

    def test_disposition_bad_input(self):
        p = "/events/2/disposition"
        self.assertEqual(self.req("POST", p, {"disposition": "maybe", "by": "U1"})[0], 400)
        self.assertEqual(self.req("POST", p, {"disposition": "approved"})[0], 400)
        self.assertEqual(self.req("POST", p, {"disposition": "approved", "by": "U1; rm -rf"})[0], 400)
        self.assertEqual(self.req("POST", p, raw=b"not json")[0], 400)
        self.assertEqual(self.req("POST", "/events/x/disposition", {"disposition": "approved", "by": "U1"})[0], 400)
        self.assertEqual(self.req("POST", "/events/999/disposition", {"disposition": "approved", "by": "U1"})[0], 404)


class CliFailureTest(unittest.TestCase):
    def test_502_when_cli_fails(self):
        port = free_port()
        env = dict(os.environ, SSW_CMD=f"{sys.executable} -c 'import sys; sys.exit(3)'",
                   SSW_API_PORT=str(port), SSW_API_HOST="127.0.0.1")
        proc = subprocess.Popen([sys.executable, str(API_DIR / "server.py")], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            url = f"http://127.0.0.1:{port}/events?status=new"
            deadline = time.time() + 10
            code = None
            while time.time() < deadline:
                try:
                    urllib.request.urlopen(url, timeout=5)
                    code = 200
                    break
                except urllib.error.HTTPError as e:
                    code = e.code
                    break
                except OSError:
                    time.sleep(0.05)
            self.assertEqual(code, 502)
        finally:
            proc.terminate()
            proc.wait(timeout=5)


class AlertUnitTest(unittest.TestCase):
    def test_confidence_rounding_and_missing_frame(self):
        a = build_alert({"id": 7, "hazard": "blocked_exit", "zone": "exit_b",
                         "ts": "2026-10-03T12:00:00", "confidence": 0.876,
                         "explanation": "Boxes block the door.", "frame_path": None})
        self.assertIn("Confidence: 88%", a["text"])
        self.assertIsNone(a["image_path"])
        self.assertTrue(a["text"].endswith("Reply `approve 7` or `false-alarm 7`."))


class RealCliNotFoundTest(unittest.TestCase):
    """The watcher's ssw prints {"error": "not found"} (with a space) and exits 1."""

    def test_not_found_with_space_maps_to_404(self):
        tmp = tempfile.TemporaryDirectory()
        stub = Path(tmp.name) / "ssw_stub.py"
        stub.write_text(
            "import json, sys\n"
            "print(json.dumps({'error': 'not found', 'id': 999}))\n"
            "sys.exit(1)\n"
        )
        port = free_port()
        env = dict(os.environ)
        env.update({
            "SSW_CMD": f"{sys.executable} {stub}",
            "SSW_API_HOST": "127.0.0.1",
            "SSW_API_PORT": str(port),
        })
        proc = subprocess.Popen([sys.executable, str(API_DIR / "server.py")], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.time() + 10
            code = None
            while time.time() < deadline:
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/events/999", timeout=2)
                except urllib.error.HTTPError as e:
                    code = e.code
                    break
                except OSError:
                    time.sleep(0.05)
            self.assertEqual(code, 404)
        finally:
            proc.terminate()
            proc.wait(timeout=5)
            tmp.cleanup()


def _ago(minutes: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(timespec="seconds")


def _row(id_, zone, status, ts_min_ago, decided_min_ago=None):
    return {"id": id_, "ts": _ago(ts_min_ago), "clip": f"cam_{zone}", "hazard": "blocked_exit",
            "zone": zone, "confidence": 0.9, "explanation": "Boxes block the exit.",
            "frame_path": None, "dedup_key": f"k{id_}", "status": status,
            "disposition_by": "U1" if decided_min_ago is not None else None,
            "disposition_ts": _ago(decided_min_ago) if decided_min_ago is not None else None}


class StatsApiTest(ServerCase):
    def seed_events(self):
        return [
            _row(1, "exit_a", "new", 5),
            _row(2, "exit_a", "posted", 25),
            _row(3, "exit_b", "posted", 3),
            _row(4, "exit_a", "approved", 120, decided_min_ago=110),
            _row(5, "exit_b", "false_alarm", 60, decided_min_ago=56),
            _row(6, "exit_a", "approved", 60 * 30, decided_min_ago=60 * 30 - 1),
        ]

    def test_stats_default_24h(self):
        code, body = self.req("GET", "/stats")
        self.assertEqual(code, 200)
        self.assertEqual(body["total"], 5)
        self.assertEqual(body["by_status"],
                         {"new": 1, "posted": 2, "approved": 1, "false_alarm": 1, "resolved": 0})
        self.assertEqual(body["by_zone"]["exit_a"],
                         {"total": 3, "open": 2, "approved": 1, "false_alarm": 0, "resolved": 0})
        self.assertEqual(body["open_event_ids"], [2, 1, 3])
        self.assertEqual(body["median_minutes_to_decision"], 7.0)
        self.assertAlmostEqual(body["longest_open_minutes"], 25.0, delta=0.5)

    def test_stats_hours_param(self):
        self.assertEqual(self.req("GET", "/stats?hours=48")[1]["total"], 6)
        self.assertEqual(self.req("GET", "/stats?hours=0.5")[1]["total"], 3)
        for bad in ("abc", "-1", "0", "nan", "100000"):
            self.assertEqual(self.req("GET", f"/stats?hours={bad}")[0], 400, bad)

    def test_digest(self):
        code, body = self.req("GET", "/digest?hours=24")
        self.assertEqual(code, 200)
        lines = body["text"].splitlines()
        self.assertEqual(lines[0], "*Site Safety Watch: last 24 h*")
        self.assertLessEqual(len(lines), 8)
        self.assertIn("#2", body["text"])
        self.assertNotIn("\u2014", body["text"])
        self.assertEqual(self.req("GET", "/digest?hours=0.01")[1],
                         {"text": "No hazards in the last 0.01 h."})
        self.assertEqual(self.req("GET", "/digest?hours=x")[0], 400)

    def test_escalations_once_per_event(self):
        code, body = self.req("GET", "/escalations")
        self.assertEqual(code, 200)
        self.assertEqual(body["event_ids"], [2])
        self.assertTrue(body["text"].startswith("Escalation: event 2 (Exit route blocked, exit_a)"))
        self.assertTrue(body["text"].endswith("Reply `approve 2` or `false-alarm 2`."))
        self.assertEqual(self.req("GET", "/escalations"), (200, {"text": "NO_REPLY"}))
        code, body = self.req("GET", "/escalations?after_min=1")
        self.assertEqual(body["event_ids"], [3])
        self.assertEqual(self.req("GET", "/escalations?after_min=-5")[0], 400)


if __name__ == "__main__":
    unittest.main()
