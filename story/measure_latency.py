"""Measure detection latency on the box during a realtime replay.

Detection latency is the time from the hazard becoming visible in the replay to the moment
the watcher records the event. It equals the event time minus (the replay start time plus
the hazard start second from labels.csv).

Run this on the box, pointed at the same database the watcher writes to, and start the
realtime replay of the hazard clip right after it begins timing. It waits for the first new
event in the zone and prints the latency as JSON. Every number it prints is measured.

Usage (box, Hemnaath):
  python -m story.measure_latency --db data/ssw.db --zone exit_a --hazard-start-sec 4
  # then immediately start: story/replay.sh data/clips/01_blocked_exit_exit_a.mp4
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path


def _parse_iso(ts: str) -> float:
    return datetime.fromisoformat(ts).timestamp()


def detection_latency_sec(stream_start_epoch: float, hazard_start_sec: float,
                          event_epoch: float) -> float:
    """Seconds from the hazard becoming visible to the event being recorded."""
    return event_epoch - (stream_start_epoch + hazard_start_sec)


def wait_for_event(db_path, zone, after_epoch, *, timeout_sec=120.0, poll_sec=1.0):
    """Return the first event (as a dict) in the zone recorded at or after after_epoch."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, ts, hazard, zone FROM events WHERE zone = ? ORDER BY id",
                (zone,),
            ).fetchall()
        finally:
            conn.close()
        for r in rows:
            try:
                if _parse_iso(r["ts"]) >= after_epoch:
                    return {"id": r["id"], "ts": r["ts"],
                            "hazard": r["hazard"], "zone": r["zone"]}
            except ValueError:
                continue
        time.sleep(poll_sec)
    return None


def main(argv=None):
    p = argparse.ArgumentParser(description="Measure detection latency during a realtime replay")
    p.add_argument("--db", required=True, help="the watcher database the replay writes to")
    p.add_argument("--zone", required=True)
    p.add_argument("--hazard-start-sec", type=float, required=True,
                   help="second the hazard appears in the clip (from labels.csv)")
    p.add_argument("--timeout", type=float, default=120.0)
    args = p.parse_args(argv)

    start = time.time()
    print(f"timing started at {datetime.now().isoformat(timespec='seconds')}, "
          "start the realtime replay now", flush=True)
    ev = wait_for_event(args.db, args.zone, start, timeout_sec=args.timeout)
    if not ev:
        print(json.dumps({"detection_latency_sec": None,
                          "error": "no event seen before timeout"}))
        return 1
    latency = detection_latency_sec(start, args.hazard_start_sec, _parse_iso(ev["ts"]))
    print(json.dumps({"detection_latency_sec": round(latency, 2),
                      "event_id": ev["id"], "event_ts": ev["ts"], "zone": ev["zone"]},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
