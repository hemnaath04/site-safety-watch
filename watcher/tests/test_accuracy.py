"""Tests for the post-lock accuracy switches: vote, locate, box column, verifier, enhance."""
import json
import os
import tempfile
import unittest

_DIR = tempfile.mkdtemp(prefix="ssw_acc_")
os.environ.setdefault("SSW_DB", os.path.join(_DIR, "ssw.db"))
os.environ.setdefault("SSW_DECISIONS", os.path.join(_DIR, "decisions.jsonl"))

from watcher import enhance, locate, rules, store, vision, voting, zones  # noqa: E402
from watcher import watcher as watcher_mod  # noqa: E402


def _noop(_m):
    pass


class TestVoteParsing(unittest.TestCase):
    def test_ratio(self):
        self.assertEqual(voting.parse_vote("3/4"), (3, 4))

    def test_single_int(self):
        self.assertEqual(voting.parse_vote("2"), (2, 2))

    def test_off_and_malformed(self):
        for bad in ("", "x", "5/4", "0/3", "-1/2", "3/0"):
            self.assertIsNone(voting.parse_vote(bad), bad)


class TestVoter(unittest.TestCase):
    def test_three_of_four(self):
        v = voting.Voter(3, 4)
        results = [v.observe("z", p) for p in (True, True, False, True)]
        self.assertEqual(results, [False, False, False, True])

    def test_window_evicts_old_hits(self):
        v = voting.Voter(2, 2)
        self.assertFalse(v.observe("z", True))   # [T]
        self.assertTrue(v.observe("z", True))     # [T,T] -> 2 of 2
        self.assertFalse(v.observe("z", False))   # [T,F] -> 1 of 2

    def test_zones_are_independent(self):
        v = voting.Voter(2, 3)
        v.observe("a", True)
        self.assertFalse(v.observe("b", True))


class TestLocate(unittest.TestCase):
    def test_full_overlap(self):
        self.assertEqual(locate.overlap_fraction([10, 10, 10, 10], [0, 0, 100, 100]), 1.0)

    def test_no_overlap(self):
        self.assertEqual(locate.overlap_fraction([0, 0, 10, 10], [100, 100, 10, 10]), 0.0)

    def test_half_overlap(self):
        self.assertAlmostEqual(
            locate.overlap_fraction([0, 0, 10, 10], [5, 0, 10, 10]), 0.5)

    def test_in_zone_threshold(self):
        self.assertTrue(locate.in_zone([0, 0, 10, 10], [5, 0, 10, 10], 0.1))
        self.assertFalse(locate.in_zone([0, 0, 10, 10], [100, 100, 10, 10], 0.1))


class TestBoxColumn(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect()
        self.conn.execute("DELETE FROM events")
        self.conn.commit()

    def test_box_round_trips(self):
        row = store.insert_event(
            self.conn, clip="c", hazard="blocked_exit", zone="zb", confidence=0.9,
            explanation="x", frame_path="f", dedup_key="k", box=[1, 2, 3, 4])
        got = store.get_event(self.conn, row["id"])
        self.assertEqual(json.loads(got["box"]), [1, 2, 3, 4])

    def test_box_defaults_null(self):
        row = store.insert_event(
            self.conn, clip="c", hazard="blocked_exit", zone="zb2", confidence=0.9,
            explanation="x", frame_path="f", dedup_key="k2")
        self.assertIsNone(store.get_event(self.conn, row["id"])["box"])


class TestZonesFile(unittest.TestCase):
    def test_exit_box_from_file(self):
        p = os.path.join(_DIR, "zones.json")
        with open(p, "w") as f:
            json.dump({"exit_a": {"exit_box": [1, 2, 3, 4]}, "exit_b": {"exit_box": None}}, f)
        self.assertEqual(zones.exit_box("exit_a", path=p), [1, 2, 3, 4])
        self.assertIsNone(zones.exit_box("exit_b", path=p))
        self.assertIsNone(zones.exit_box("missing", path=p))

    def test_missing_file_is_safe(self):
        self.assertEqual(zones.load_zones(path=os.path.join(_DIR, "nope.json")), {})


class TestRulesBox(unittest.TestCase):
    def test_box_optional_valid(self):
        self.assertTrue(rules.validate_event(
            {"hazard": "blocked_exit", "confidence": 0.9, "explanation": "x",
             "box": [1, 2, 3, 4]}))

    def test_box_may_be_null(self):
        self.assertTrue(rules.validate_event(
            {"hazard": "none", "confidence": 0.9, "explanation": "x", "box": None}))

    def test_bad_box_rejected(self):
        self.assertFalse(rules.validate_event(
            {"hazard": "blocked_exit", "confidence": 0.9, "explanation": "x",
             "box": [1, 2, 3]}))


class TestHandleSwitches(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect()
        self.conn.execute("DELETE FROM events")
        self.conn.commit()

    def test_vote_holds_then_fires(self):
        client = vision.FakeVision()          # always blocked_exit
        voter = voting.Voter(2, 3)
        r1 = watcher_mod._handle(self.conn, client, None, "c", "zv", _noop,
                                 voter=voter, do_blur=False)
        r2 = watcher_mod._handle(self.conn, client, None, "c", "zv", _noop,
                                 voter=voter, do_blur=False)
        self.assertIsNone(r1)        # 1 of 3, held
        self.assertIsNotNone(r2)     # 2 of 3, fires

    def test_locate_filters_out_of_zone(self):
        client = vision.FakeVision(box=[0, 0, 10, 10])
        row = watcher_mod._handle(self.conn, client, None, "c", "zl", _noop,
                                  locate=True, zone_box=[100, 100, 10, 10], do_blur=False)
        self.assertIsNone(row)

    def test_locate_keeps_in_zone_and_stores_box(self):
        client = vision.FakeVision(box=[10, 10, 10, 10])
        row = watcher_mod._handle(self.conn, client, None, "c", "zl2", _noop,
                                  locate=True, zone_box=[0, 0, 100, 100], do_blur=False)
        self.assertIsNotNone(row)
        self.assertEqual(json.loads(row["box"]), [10, 10, 10, 10])

    def test_verifier_rejection_filters(self):
        client = vision.FakeVision()
        row = watcher_mod._handle(self.conn, client, None, "c", "zver", _noop,
                                  verify=lambda j, z: False, do_blur=False)
        self.assertIsNone(row)

    def test_verifier_accept_stores(self):
        client = vision.FakeVision()
        row = watcher_mod._handle(self.conn, client, None, "c", "zver2", _noop,
                                  verify=lambda j, z: True, do_blur=False)
        self.assertIsNotNone(row)


class TestEnhanceSafe(unittest.TestCase):
    def test_enhance_returns_input_and_no_transform_on_bad_input(self):
        # With or without OpenCV, a non-image input comes back unchanged with no transform.
        out, transform = enhance.enhance_jpeg(b"not-an-image")
        self.assertEqual(out, b"not-an-image")
        self.assertIsNone(transform)

    def test_untransform_box_maps_back_to_original(self):
        # box in enhanced coords -> original coords given crop offset and 2x scale
        box = enhance.untransform_box([10, 10, 20, 20],
                                      {"ox": 100, "oy": 50, "scale": 2.0})
        self.assertEqual(box, [105.0, 55.0, 10.0, 10.0])

    def test_untransform_box_noop_without_transform(self):
        self.assertEqual(enhance.untransform_box([1, 2, 3, 4], None), [1, 2, 3, 4])


class TestVisionMapping(unittest.TestCase):
    def test_blocked_exit_maps_from_visible_and_blocked(self):
        ev = vision.to_event(
            {"exit_visible": True, "blocked": True, "box": [1, 2, 3, 4],
             "confidence": 0.9, "explanation": "cart"}, "exit_a")
        self.assertEqual(ev["hazard"], "blocked_exit")
        self.assertEqual(ev["zone"], "exit_a")
        self.assertEqual(ev["box"], [1, 2, 3, 4])
        self.assertTrue(rules.validate_event(ev))

    def test_visible_but_not_blocked_is_none(self):
        ev = vision.to_event(
            {"exit_visible": True, "blocked": False, "box": None,
             "confidence": 0.9, "explanation": "clear"}, "z")
        self.assertEqual(ev["hazard"], "none")
        self.assertIsNone(ev["box"])

    def test_not_visible_is_none(self):
        ev = vision.to_event(
            {"exit_visible": False, "blocked": True, "box": [1, 2, 3, 4],
             "confidence": 0.9, "explanation": "no exit in frame"}, "z")
        self.assertEqual(ev["hazard"], "none")
        self.assertIsNone(ev["box"])  # box dropped when not a blocked exit


class TestLocalTime(unittest.TestCase):
    def test_now_iso_is_timezone_aware_local(self):
        from datetime import datetime
        s = store.now_iso()
        dt = datetime.fromisoformat(s)
        self.assertIsNotNone(dt.tzinfo)
        # offset matches this machine's local offset
        self.assertEqual(dt.utcoffset(), datetime.now().astimezone().utcoffset())


if __name__ == "__main__":
    unittest.main()
