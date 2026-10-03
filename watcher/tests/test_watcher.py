"""Watcher unit tests. Stdlib unittest only, so they run anywhere with no extra deps.

Run from the repo root:
  python -m unittest discover -s watcher/tests -v
"""
import os
import tempfile
import unittest
from datetime import timedelta

# Point the store at a throwaway db before importing the package.
_TMP = tempfile.mkdtemp(prefix="ssw_test_")
os.environ["SSW_DB"] = os.path.join(_TMP, "ssw.db")

from watcher import dedup, rules, store, vision, zones  # noqa: E402
from watcher import watcher as watcher_mod  # noqa: E402
from watcher.sampler import now_local  # noqa: E402


class TestRules(unittest.TestCase):
    def test_valid_event_ok(self):
        self.assertTrue(rules.validate_event(
            {"hazard": "blocked_exit", "zone": "exit_a", "confidence": 0.9,
             "explanation": "cart in the doorway"}))

    def test_valid_event_rejects_bad_hazard(self):
        self.assertFalse(rules.validate_event(
            {"hazard": "fire", "zone": "exit_a", "confidence": 0.9, "explanation": "x"}))

    def test_valid_event_rejects_bad_confidence(self):
        self.assertFalse(rules.validate_event(
            {"hazard": "none", "zone": "exit_a", "confidence": 2.0, "explanation": "x"}))

    def test_lookup_rule(self):
        r = rules.lookup_rule("blocked_exit")
        self.assertEqual(r["cite"], "29 CFR 1910.37")
        self.assertTrue(r["fix"])

    def test_lookup_unknown_rule_is_empty(self):
        self.assertEqual(rules.lookup_rule("spill")["cite"], "")


class TestZones(unittest.TestCase):
    def test_override_wins(self):
        self.assertEqual(zones.resolve_zone("anything.mp4", override="dock_3"), "dock_3")

    def test_from_table(self):
        self.assertEqual(zones.resolve_zone("fake_cam"), "exit_a")

    def test_from_name(self):
        self.assertEqual(zones.resolve_zone("01_blocked_exit_exitB.mp4"), "exitb")


class TestStore(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect()
        self.conn.execute("DELETE FROM events")
        self.conn.commit()

    def _insert(self, zone="exit_a", key="k1"):
        return store.insert_event(
            self.conn, clip="c.mp4", hazard="blocked_exit", zone=zone,
            confidence=0.9, explanation="x", frame_path="data/frames/x.jpg", dedup_key=key)

    def test_insert_and_get(self):
        row = self._insert()
        got = store.get_event(self.conn, row["id"])
        self.assertEqual(got["status"], "new")
        self.assertEqual(got["hazard"], "blocked_exit")

    def test_dispose_flow(self):
        row = self._insert()
        store.mark_posted(self.conn, row["id"])
        self.assertEqual(store.get_event(self.conn, row["id"])["status"], "posted")
        done = store.dispose(self.conn, row["id"], "approved", "U_x")
        self.assertEqual(done["status"], "approved")
        self.assertEqual(done["disposition_by"], "U_x")
        self.assertTrue(done["disposition_ts"])

    def test_dispose_rejects_bad_status(self):
        row = self._insert()
        with self.assertRaises(ValueError):
            store.dispose(self.conn, row["id"], "deleted", "U_x")

    def test_events_by_status(self):
        self._insert(key="k1")
        self.assertEqual(len(store.events_by_status(self.conn, "new")), 1)
        self.assertEqual(len(store.events_by_status(self.conn, "approved")), 0)


class TestDedup(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect()
        self.conn.execute("DELETE FROM events")
        self.conn.commit()

    def test_duplicate_within_window(self):
        when = now_local()
        key = dedup.make_dedup_key("blocked_exit", "exit_a", when, 5)
        store.insert_event(self.conn, clip="c", hazard="blocked_exit", zone="exit_a",
                           confidence=0.9, explanation="x", frame_path="f", dedup_key=key)
        self.assertTrue(dedup.is_duplicate(self.conn, "blocked_exit", "exit_a", when))

    def test_not_duplicate_other_zone(self):
        when = now_local()
        key = dedup.make_dedup_key("blocked_exit", "exit_a", when, 5)
        store.insert_event(self.conn, clip="c", hazard="blocked_exit", zone="exit_a",
                           confidence=0.9, explanation="x", frame_path="f", dedup_key=key)
        self.assertFalse(dedup.is_duplicate(self.conn, "blocked_exit", "dock_3", when))


class TestFakeVision(unittest.TestCase):
    def test_default_reports_blocked_exit(self):
        ev = vision.FakeVision().classify(None, "exit_a")
        self.assertEqual(ev["hazard"], "blocked_exit")
        self.assertEqual(ev["zone"], "exit_a")
        self.assertTrue(rules.validate_event(ev))

    def test_script_sequence(self):
        c = vision.FakeVision(script=["none", "blocked_exit"])
        self.assertEqual(c.classify(None, "z")["hazard"], "none")
        self.assertEqual(c.classify(None, "z")["hazard"], "blocked_exit")


class TestRunEndToEnd(unittest.TestCase):
    def setUp(self):
        conn = store.connect()
        conn.execute("DELETE FROM events")
        conn.commit()

    def test_run_creates_one_event_then_dedups(self):
        made = watcher_mod.run("fake_cam", fake=True, no_frames=True)
        self.assertEqual(len(made), 1)
        self.assertEqual(made[0]["hazard"], "blocked_exit")
        # second run in the same zone is a duplicate, so no new event
        again = watcher_mod.run("fake_cam", fake=True, no_frames=True)
        self.assertEqual(len(again), 0)


if __name__ == "__main__":
    unittest.main()
