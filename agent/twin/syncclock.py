"""Shared playback clock for cameras that filmed the same moment from different angles.

All cameras in one sync group share t = (now - t0) mod loop_len. Each camera shows its own file
at start_offset_s + t. loop_len is the shortest (duration - start_offset_s) in the group, so every
member has footage for the whole loop. Pure code, no video, so it is unit tested.
"""

import math
import threading
import time

DRIFT_SEEK_S = 0.5
MAX_GRAB = 30


def loop_length(entries):
    """entries: {cam_id: (duration_s, start_offset_s)}. Returns (loop_len, usable_cam_ids).

    Cameras whose offset leaves no footage (duration - offset <= 0) are left out.
    """
    usable = {cid: d - off for cid, (d, off) in entries.items()
              if math.isfinite(d) and math.isfinite(off) and d - off > 0}
    if not usable:
        return None, []
    return min(usable.values()), sorted(usable)


def shared_time(now, t0, loop_len):
    """(t, cycle): position on the shared timeline and how many loops have completed."""
    elapsed = max(0.0, now - t0)
    cycle = int(elapsed // loop_len)
    return elapsed - cycle * loop_len, cycle


def file_position(start_offset_s, t):
    return start_offset_s + t


def plan_step(next_idx, target_pos_s, fps, new_cycle):
    """Decide the reader's next action.

    next_idx: index of the frame the capture will return on the next read.
    target_pos_s: where this camera's file should be now. Returns one of
    ("seek", frame_idx), ("sleep", seconds), ("grab", count), ("read", None).
    Seek on a new loop or when more than DRIFT_SEEK_S off; otherwise read in order.
    """
    target_idx = int(target_pos_s * fps)
    drift_s = (next_idx - target_idx) / fps
    if new_cycle or abs(drift_s) > DRIFT_SEEK_S:
        return "seek", target_idx
    if next_idx > target_idx:
        return "sleep", (next_idx / fps) - target_pos_s
    behind = target_idx - next_idx
    if behind >= 1:
        return "grab", min(behind, MAX_GRAB)
    return "read", None


class SyncGroup:
    """Members register their file duration; the clock starts once all have registered or
    after wait_s, whichever comes first. Thread safe."""

    def __init__(self, name, offsets: dict, wait_s=10.0, clock=time.monotonic):
        self.name = name
        self.offsets = dict(offsets)
        self.wait_s = wait_s
        self.clock = clock
        self.durations = {}
        self.t0 = None
        self.loop_len = None
        self.members = []
        self.cond = threading.Condition()
        self.first_seen = None

    def register(self, cam_id, duration_s):
        with self.cond:
            if self.first_seen is None:
                self.first_seen = self.clock()
            self.durations[cam_id] = float(duration_s)
            if self.t0 is None and set(self.durations) >= set(self.offsets):
                self._start()
            self.cond.notify_all()

    def _start(self):
        entries = {cid: (d, self.offsets.get(cid, 0.0)) for cid, d in self.durations.items()}
        loop_len, members = loop_length(entries)
        if loop_len is None:
            return
        self.loop_len, self.members, self.t0 = loop_len, members, self.clock()

    def wait_ready(self):
        """Block until the clock has started. Returns True if this group is usable."""
        with self.cond:
            while self.t0 is None:
                waited = self.clock() - (self.first_seen or self.clock())
                if waited >= self.wait_s:
                    self._start()
                    if self.t0 is None:
                        return False
                    self.cond.notify_all()
                    break
                self.cond.wait(timeout=min(0.5, self.wait_s - waited))
            return True

    def now(self):
        """(t, cycle) or (None, None) before the clock starts."""
        with self.cond:
            if self.t0 is None:
                return None, None
            return shared_time(self.clock(), self.t0, self.loop_len)

    def view(self):
        t, _ = self.now()
        if t is None:
            return {"t": None, "loop_len": None, "cams": []}
        return {"t": round(t, 3), "loop_len": round(self.loop_len, 3), "cams": list(self.members)}
