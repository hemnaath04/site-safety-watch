"""Stress and edge-case coverage for the Watcher: things a hazard day throws at it that the
happy-path tests do not. Legacy-db migration, malformed model output, box-conversion
extremes, zone-config robustness, and ssw JSON validity under bad input.
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_DIR = tempfile.mkdtemp(prefix="ssw_stress_")
os.environ.setdefault("SSW_DB", os.path.join(_DIR, "ssw.db"))
os.environ.setdefault("SSW_DECISIONS", os.path.join(_DIR, "dec.jsonl"))
os.environ.setdefault("SSW_TZ", "America/New_York")

from watcher import enhance, locate, rules, store, vision, zones  # noqa: E402
from watcher import watcher as W  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]


class TestMalformedTotality(unittest.TestCase):
    GARBAGE = [
        None, {}, [], "x", 42,
        {"hazard": "fire", "confidence": 0.5, "explanation": "x"},
        {"hazard": "blocked_exit", "confidence": "high", "explanation": "x"},
        {"hazard": "blocked_exit", "confidence": 2.0, "explanation": "x"},
        {"hazard": "blocked_exit", "confidence": -0.1, "explanation": "x"},
        {"hazard": "blocked_exit", "confidence": 0.9, "explanation": 5},
        {"hazard": "blocked_exit", "confidence": 0.9, "explanation": "x", "box": [1, 2, 3]},
        {"hazard": "blocked_exit", "confidence": 0.9, "explanation": "x", "box": "oops"},
        {"hazard": "blocked_exit", "confidence": 0.9, "explanation": "x", "box": [1, 2, -3, 4]},
    ]

    def test_validate_rejects_all_garbage_without_crashing(self):
        for g in self.GARBAGE:
            self.assertFalse(rules.validate_event(g), g)

    def test_to_event_is_total(self):
        raws = [
            {}, {"exit_visible": True, "blocked": True},
            {"exit_visible": True, "blocked": False, "box": [1, 2, 3, 4],
             "confidence": 0.9, "explanation": "clear"},
            {"exit_visible": False, "blocked": True, "box": [1, 2, 3, 4],
             "confidence": 0.9, "explanation": "no exit"},
            {"exit_visible": "yes", "blocked": 1, "confidence": None, "explanation": None},
        ]
        for r in raws:
            ev = vision.to_event(r, "z")
            self.assertIn(ev["hazard"], ("blocked_exit", "none"))
            self.assertIsInstance(ev["confidence"], float)
            if ev["hazard"] == "none":
                self.assertIsNone(ev["box"])


class TestBoxConversionExtremes(unittest.TestCase):
    def test_hemnaath_example(self):
        out = [round(v, 1) for v in locate.qwen_xyxy1000_to_xywh([270, 600, 669, 918], 960, 1706)]
        self.assertEqual(out, [259.2, 1023.6, 383.0, 542.5])

    def test_flipped_corners_positive_size(self):
        out = locate.qwen_xyxy1000_to_xywh([900, 900, 100, 100], 1000, 1000)
        self.assertGreater(out[2], 0)
        self.assertGreater(out[3], 0)

    def test_bad_len_and_zero_dims_passthrough(self):
        self.assertEqual(locate.qwen_xyxy1000_to_xywh([1, 2, 3], 960, 540), [1, 2, 3])
        self.assertEqual(locate.qwen_xyxy1000_to_xywh([1, 2, 3, 4], 0, 0), [1, 2, 3, 4])

    def test_untransform_round_trip(self):
        self.assertEqual(enhance.untransform_box([10, 10, 20, 20],
                         {"ox": 100, "oy": 50, "scale": 2.0}), [105.0, 55.0, 10.0, 10.0])

    def test_enhance_bad_input_safe(self):
        out, transform = enhance.enhance_jpeg(b"not-an-image")
        self.assertEqual(out, b"not-an-image")
        self.assertIsNone(transform)


class TestLegacyMigration(unittest.TestCase):
    def test_old_schema_db_migrates_and_stays_usable(self):
        legacy = os.path.join(_DIR, "legacy.db")
        con = sqlite3.connect(legacy)
        con.execute(
            "CREATE TABLE events (id INTEGER PRIMARY KEY, ts TEXT, clip TEXT, hazard TEXT, "
            "zone TEXT, confidence REAL, explanation TEXT, frame_path TEXT, dedup_key TEXT, "
            "status TEXT, disposition_by TEXT, disposition_ts TEXT)")
        con.execute(
            "INSERT INTO events (ts,clip,hazard,zone,confidence,explanation,frame_path,"
            "dedup_key,status) VALUES ('2026-10-03T10:00:00-04:00','c','blocked_exit',"
            "'exit_a',0.9,'x','f','k','new')")
        con.commit(); con.close()
        conn = store.connect(legacy)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(events)")]
        for c in ("box", "resolved_ts", "resolved_frame_path", "time_to_clear_sec",
                  "resolved_announced"):
            self.assertIn(c, cols)
        self.assertEqual(store.get_event(conn, 1)["hazard"], "blocked_exit")
        done = store.resolve_event(conn, 1, resolved_ts="t", resolved_frame_path="rf",
                                   time_to_clear_sec=5.0)
        self.assertEqual(done["status"], "resolved")


class TestZonesRobustness(unittest.TestCase):
    def test_malformed_and_missing_safe(self):
        bad = os.path.join(_DIR, "bad.json")
        open(bad, "w").write("{ not valid json ")
        self.assertEqual(zones.load_zones(bad), {})
        self.assertEqual(zones.load_zones(os.path.join(_DIR, "nope.json")), {})
        self.assertIsNone(zones.exit_box("does_not_exist", path=bad))


class TestSswJsonValidity(unittest.TestCase):
    def _ssw(self, *args):
        env = dict(os.environ)
        r = subprocess.run([sys.executable, "-m", "watcher.ssw", *args],
                           capture_output=True, text=True, cwd=str(_REPO), env=env)
        return r.stdout.strip(), r.returncode

    def test_commands_emit_json_or_no_reply(self):
        conn = store.connect()
        conn.execute("DELETE FROM events"); conn.commit()
        W.run("fake_cam", fake=True, no_frames=True, do_blur=False)
        for cmd in (["events", "--status", "new"], ["event", "1"], ["rule", "blocked_exit"],
                    ["pending"], ["pending-resolved"]):
            out, _ = self._ssw(*cmd)
            if out != "NO_REPLY":
                json.loads(out)  # raises if invalid

    def test_bad_id_is_error_json_exit_1(self):
        out, rc = self._ssw("event", "999999")
        self.assertEqual(rc, 1)
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
