"""Tests for auto-resolution: the clear-streak tracker, the store funcs, and the loop."""
import os
import tempfile
import unittest

_DIR = tempfile.mkdtemp(prefix="ssw_res_")
os.environ.setdefault("SSW_DB", os.path.join(_DIR, "ssw.db"))
os.environ.setdefault("SSW_DECISIONS", os.path.join(_DIR, "decisions.jsonl"))

from watcher import resolve, store, vision  # noqa: E402
from watcher import watcher as watcher_mod  # noqa: E402


def _noop(_m):
    pass


class TestResolver(unittest.TestCase):
    def test_two_in_a_row_triggers_once(self):
        r = resolve.Resolver(clears_required=2)
        self.assertFalse(r.observe("z", True))   # 1
        self.assertTrue(r.observe("z", True))     # 2 -> trigger
        self.assertFalse(r.observe("z", True))    # 3 -> nothing left

    def test_hazard_resets_streak(self):
        r = resolve.Resolver(clears_required=2)
        self.assertFalse(r.observe("z", True))
        self.assertFalse(r.observe("z", False))   # reset
        self.assertFalse(r.observe("z", True))     # back to 1
        self.assertTrue(r.observe("z", True))      # 2 -> trigger

    def test_zones_independent(self):
        r = resolve.Resolver(clears_required=2)
        r.observe("a", True)
        self.assertFalse(r.observe("b", True))


class TestStoreResolve(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect()
        self.conn.execute("DELETE FROM events")
        self.conn.commit()

    def _new(self, zone="z"):
        return store.insert_event(
            self.conn, clip="c", hazard="blocked_exit", zone=zone, confidence=0.9,
            explanation="x", frame_path="f", dedup_key="k", box=[1, 2, 3, 4])

    def test_active_events_then_resolve(self):
        ev = self._new("zr")
        self.assertEqual(len(store.active_events(self.conn, "zr")), 1)
        done = store.resolve_event(
            self.conn, ev["id"], resolved_ts="2026-10-03T14:00:00-04:00",
            resolved_frame_path="rf.jpg", time_to_clear_sec=42.0)
        self.assertEqual(done["status"], "resolved")
        self.assertEqual(done["time_to_clear_sec"], 42.0)
        self.assertEqual(done["resolved_frame_path"], "rf.jpg")
        self.assertEqual(len(store.active_events(self.conn, "zr")), 0)

    def test_pending_resolved_and_announce(self):
        ev = self._new("zp")
        store.resolve_event(self.conn, ev["id"], resolved_ts="t",
                            resolved_frame_path="f", time_to_clear_sec=1.0)
        self.assertEqual(len(store.pending_resolved(self.conn)), 1)
        store.mark_resolved_announced(self.conn, ev["id"])
        self.assertEqual(len(store.pending_resolved(self.conn)), 0)


class TestResolveInLoop(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect()
        self.conn.execute("DELETE FROM events")
        self.conn.commit()

    def test_clear_streak_resolves_open_event(self):
        resolver = resolve.Resolver(clears_required=2)
        # a hazard opens an event
        blocked = vision.FakeVision(script=["blocked_exit"])
        row = watcher_mod._handle(self.conn, blocked, None, "c", "zx", _noop,
                                  resolver=resolver, do_blur=False)
        self.assertIsNotNone(row)
        self.assertEqual(len(store.active_events(self.conn, "zx")), 1)
        # two clear checks in a row resolve it
        clear = vision.FakeVision(script=["none", "none"])
        watcher_mod._handle(self.conn, clear, None, "c", "zx", _noop,
                            resolver=resolver, do_blur=False)
        self.assertEqual(len(store.active_events(self.conn, "zx")), 1)  # one clear, not yet
        watcher_mod._handle(self.conn, clear, None, "c", "zx", _noop,
                            resolver=resolver, do_blur=False)
        active = store.active_events(self.conn, "zx")
        self.assertEqual(len(active), 0)  # second clear resolved it
        resolved = store.events_by_status(self.conn, "resolved")
        self.assertEqual(len(resolved), 1)
        self.assertIsNotNone(resolved[0]["resolved_ts"])
        self.assertIsNotNone(resolved[0]["time_to_clear_sec"])

    def test_single_clear_does_not_resolve(self):
        resolver = resolve.Resolver(clears_required=2)
        blocked = vision.FakeVision(script=["blocked_exit"])
        watcher_mod._handle(self.conn, blocked, None, "c", "zy", _noop,
                            resolver=resolver, do_blur=False)
        clear = vision.FakeVision(script=["none"])
        watcher_mod._handle(self.conn, clear, None, "c", "zy", _noop,
                            resolver=resolver, do_blur=False)
        self.assertEqual(len(store.active_events(self.conn, "zy")), 1)


if __name__ == "__main__":
    unittest.main()
