import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
import stats  # noqa: E402

NOW = datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)


def ev(id_, zone, status, ts, decided=None, hazard="blocked_exit"):
    return {"id": id_, "ts": ts, "hazard": hazard, "zone": zone, "status": status,
            "disposition_ts": decided, "disposition_by": "U1" if decided else None}


EVENTS = [
    ev(1, "exit_a", "new", "2026-10-03T13:50:00+00:00"),
    ev(2, "exit_a", "posted", "2026-10-03T09:15:00-04:00"),             # 13:15 UTC
    ev(3, "exit_b", "approved", "2026-10-03T12:00:00Z", "2026-10-03T12:04:30Z"),
    ev(4, "exit_b", "false_alarm", "2026-10-03T11:00:00", "2026-10-03T11:10:00"),  # naive = UTC
    ev(5, "exit_a", "approved", "2026-10-03T10:00:00+00:00", "2026-10-03T10:20:00+00:00"),
    ev(6, "exit_a", "approved", "2026-10-01T10:00:00+00:00", "2026-10-01T10:01:00+00:00"),
    ev(7, "exit_a", "new", "not a time"),
]


class ComputeStatsTest(unittest.TestCase):
    def setUp(self):
        start, end = stats.window(NOW, 24)
        self.s = stats.compute_stats(EVENTS, start, end)

    def test_window_and_totals(self):
        self.assertEqual(self.s["window"]["from"], "2026-10-02T14:00:00+00:00")
        self.assertEqual(self.s["window"]["to"], "2026-10-03T14:00:00+00:00")
        self.assertEqual(self.s["total"], 5)
        self.assertEqual(self.s["by_status"],
                         {"new": 1, "posted": 1, "approved": 2, "false_alarm": 1, "resolved": 0})

    def test_by_zone(self):
        self.assertEqual(self.s["by_zone"], {
            "exit_a": {"total": 3, "open": 2, "approved": 1, "false_alarm": 0, "resolved": 0},
            "exit_b": {"total": 2, "open": 0, "approved": 1, "false_alarm": 1, "resolved": 0},
        })

    def test_open_ids_oldest_first_and_timings(self):
        self.assertEqual(self.s["open_event_ids"], [2, 1])
        # decisions: 4.5, 10, 20 min -> median 10.0
        self.assertEqual(self.s["median_minutes_to_decision"], 10.0)
        # event 2 first seen 13:15 UTC, now 14:00
        self.assertEqual(self.s["longest_open_minutes"], 45.0)

    def test_median_rounds_to_one_decimal(self):
        rows = [ev(1, "z", "approved", "2026-10-03T13:00:00Z", "2026-10-03T13:01:20Z"),
                ev(2, "z", "approved", "2026-10-03T13:00:00Z", "2026-10-03T13:01:30Z")]
        s = stats.compute_stats(rows, *stats.window(NOW, 24))
        self.assertEqual(s["median_minutes_to_decision"], 1.4)

    def test_empty_window(self):
        s = stats.compute_stats(EVENTS, *stats.window(NOW, 0.05))
        self.assertEqual(s["total"], 0)
        self.assertEqual(s["open_event_ids"], [])
        self.assertIsNone(s["median_minutes_to_decision"])
        self.assertIsNone(s["longest_open_minutes"])
        self.assertEqual(stats.digest_text(s), "No hazards in the last 0.05 h.")


class DigestTest(unittest.TestCase):
    def test_digest_text(self):
        s = stats.compute_stats(EVENTS, *stats.window(NOW, 24))
        text = stats.digest_text(s)
        lines = text.splitlines()
        self.assertEqual(lines[0], "*Site Safety Watch: last 24 h*")
        self.assertLessEqual(len(lines), 8)
        self.assertEqual(lines[1], "5 hazards: 1 new, 1 posted, 2 approved, 1 false alarm, 0 confirmed clear.")
        self.assertIn("exit_a 3 (2 open, 1 approved, 0 false alarm)", lines[2])
        self.assertIn("exit_b 2 (0 open, 1 approved, 1 false alarm)", lines[2])
        self.assertIn("Median time to decision: 10.0 min.", text)
        self.assertIn("Open: #2, #1.", text)
        self.assertIn("Longest open: 45.0 min.", text)
        self.assertNotIn("\u2014", text)

    def test_many_open_ids_capped_and_many_zones_stay_short(self):
        rows = [ev(i, f"zone_{i}", "new", "2026-10-03T13:00:00Z") for i in range(1, 16)]
        text = stats.digest_text(stats.compute_stats(rows, *stats.window(NOW, 24)))
        self.assertLessEqual(len(text.splitlines()), 8)
        self.assertIn("and 5 more.", text)
        self.assertIn("no decisions yet.", text)


class EscalationTest(unittest.TestCase):
    def test_only_posted_older_than_threshold(self):
        rows = [
            ev(1, "exit_a", "posted", "2026-10-03T13:55:00Z"),   # 5 min
            ev(2, "exit_a", "posted", "2026-10-03T13:30:00Z"),   # 30 min
            ev(3, "exit_b", "posted", "2026-10-03T13:45:00Z"),   # 15 min
            ev(4, "exit_a", "new", "2026-10-03T12:00:00Z"),
            ev(5, "exit_a", "approved", "2026-10-03T12:00:00Z", "2026-10-03T12:05:00Z"),
            ev(6, "exit_a", "posted", "bad"),
        ]
        due = stats.escalations(rows, NOW, 10)
        self.assertEqual([e["id"] for e in due], [2, 3])
        self.assertEqual(stats.minutes_waiting(due[0], NOW), 30)

    def test_escalation_text(self):
        e = ev(9, "exit_a", "posted", "2026-10-03T13:30:00Z")
        self.assertEqual(
            stats.escalation_text(e, 30),
            "Escalation: event 9 (Exit route blocked, exit_a) has had no decision for 30 min. "
            "Reply `approve 9` or `false-alarm 9`.")


if __name__ == "__main__":
    unittest.main()


class ResolvedTextTest(unittest.TestCase):
    def test_all_clear_line_uses_measured_time(self):
        line = stats.resolved_text({"id": 7, "zone": "exit_1", "time_to_clear_sec": 192.4})
        self.assertIn("event 7", line)
        self.assertIn("exit_1", line)
        self.assertIn("3 min 12 s", line)
        self.assertNotIn(chr(0x2014), line)

    def test_short_and_missing_times(self):
        self.assertEqual(stats.format_seconds(48), "48 s")
        self.assertNotIn("Measured", stats.resolved_text({"id": 1, "zone": "a"}))

    def test_plural_and_resolved_in_digest(self):
        from datetime import datetime, timezone
        end = datetime(2026, 10, 3, 18, 0, tzinfo=timezone.utc)
        start, end = stats.window(end, 24)
        ev = {"id": 1, "ts": "2026-10-03T13:00:00-04:00", "zone": "exit_1",
              "hazard": "blocked_exit", "status": "resolved"}
        text = stats.digest_text(stats.compute_stats([ev], start, end))
        self.assertIn("1 hazard:", text)
        self.assertIn("1 confirmed clear", text)
