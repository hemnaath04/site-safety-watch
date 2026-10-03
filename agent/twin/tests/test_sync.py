import sys
import threading
import unittest
from pathlib import Path

TWIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TWIN_DIR))
import syncclock  # noqa: E402


class FakeClock:
    def __init__(self, t=100.0):
        self.t = t

    def __call__(self):
        return self.t


class LoopLengthTest(unittest.TestCase):
    def test_shortest_remaining_footage(self):
        # cam1: 60 s clip from 0 -> 60 s left; cam2: 58 s clip from 3.5 -> 54.5 s left
        loop_len, members = syncclock.loop_length({"cam1": (60.0, 0.0), "cam2": (58.0, 3.5)})
        self.assertEqual(loop_len, 54.5)
        self.assertEqual(members, ["cam1", "cam2"])

    def test_camera_with_offset_past_end_left_out(self):
        loop_len, members = syncclock.loop_length({"cam1": (30.0, 0.0), "cam2": (10.0, 12.0)})
        self.assertEqual((loop_len, members), (30.0, ["cam1"]))
        self.assertEqual(syncclock.loop_length({"a": (5.0, 5.0)}), (None, []))


class SharedTimeTest(unittest.TestCase):
    def test_offsets_and_wrap_around(self):
        t0, loop_len = 100.0, 54.5
        t, cycle = syncclock.shared_time(110.0, t0, loop_len)
        self.assertEqual((t, cycle), (10.0, 0))
        # same instant: each camera at its own offset
        self.assertEqual(syncclock.file_position(0.0, t), 10.0)
        self.assertEqual(syncclock.file_position(3.5, t), 13.5)
        # wraps after one loop and counts the cycle
        t, cycle = syncclock.shared_time(100.0 + 54.5 + 2.0, t0, loop_len)
        self.assertAlmostEqual(t, 2.0)
        self.assertEqual(cycle, 1)
        t, cycle = syncclock.shared_time(100.0 + 3 * 54.5, t0, loop_len)
        self.assertAlmostEqual(t, 0.0)
        self.assertEqual(cycle, 3)

    def test_before_t0_clamps_to_zero(self):
        self.assertEqual(syncclock.shared_time(90.0, 100.0, 10.0), (0.0, 0))


class PlanStepTest(unittest.TestCase):
    def test_new_cycle_seeks_to_target(self):
        self.assertEqual(syncclock.plan_step(500, 3.5, 30.0, True), ("seek", 105))

    def test_large_drift_seeks(self):
        self.assertEqual(syncclock.plan_step(0, 10.0, 30.0, False), ("seek", 300))
        self.assertEqual(syncclock.plan_step(330, 10.0, 30.0, False), ("seek", 300))

    def test_ahead_sleeps_until_frame_time(self):
        action, secs = syncclock.plan_step(301, 10.0, 30.0, False)
        self.assertEqual(action, "sleep")
        self.assertAlmostEqual(secs, 301 / 30.0 - 10.0)

    def test_small_lag_grabs_then_on_time_reads(self):
        self.assertEqual(syncclock.plan_step(295, 10.0, 30.0, False), ("grab", 5))
        self.assertEqual(syncclock.plan_step(300, 10.0, 30.0, False), ("read", None))


class SyncGroupTest(unittest.TestCase):
    def test_clock_starts_when_all_registered(self):
        clock = FakeClock(100.0)
        g = syncclock.SyncGroup("demo", {"cam1": 0.0, "cam2": 3.5}, clock=clock)
        g.register("cam1", 60.0)
        self.assertEqual(g.now(), (None, None))
        self.assertEqual(g.view(), {"t": None, "loop_len": None, "cams": []})
        clock.t = 101.0
        g.register("cam2", 58.0)
        self.assertTrue(g.wait_ready())
        self.assertEqual(g.loop_len, 54.5)
        clock.t = 101.0 + 54.5 + 1.25
        self.assertEqual(g.view(), {"t": 1.25, "loop_len": 54.5, "cams": ["cam1", "cam2"]})
        # both cameras land on the same shared instant
        t, _ = g.now()
        self.assertAlmostEqual(syncclock.file_position(g.offsets["cam2"], t)
                               - syncclock.file_position(g.offsets["cam1"], t), 3.5)

    def test_starts_without_missing_member_after_wait(self):
        g = syncclock.SyncGroup("demo", {"cam1": 0.0, "cam2": 0.0}, wait_s=0.2)
        g.register("cam1", 20.0)
        result = {}
        th = threading.Thread(target=lambda: result.update(ok=g.wait_ready()))
        th.start()
        th.join(timeout=5)
        self.assertTrue(result.get("ok"))
        self.assertEqual((g.loop_len, g.members), (20.0, ["cam1"]))

    def test_unusable_group_reports_not_ready(self):
        g = syncclock.SyncGroup("demo", {"cam1": 50.0}, wait_s=0.1)
        g.register("cam1", 20.0)
        self.assertFalse(g.wait_ready())


if __name__ == "__main__":
    unittest.main()
