"""Temporal voting: only promote a hazard seen in N of the last M samples.

Cuts single-frame false alarms on shaky CCTV. Pure Python, fully unit tested. Off unless
SSW_VOTE is set (for example SSW_VOTE=3/4 means 3 of the last 4 samples).
"""
from __future__ import annotations

from collections import deque


def parse_vote(spec: str):
    """Parse '3/4' into (need, window). Returns None when off or malformed."""
    if not spec:
        return None
    try:
        if "/" in spec:
            need_s, win_s = spec.split("/", 1)
            need, window = int(need_s), int(win_s)
        else:
            need = int(spec)
            window = need
    except (ValueError, TypeError):
        return None
    if need <= 0 or window <= 0 or need > window:
        return None
    return need, window


class Voter:
    """Per-zone sliding window of recent sample results (hazard present or not)."""

    def __init__(self, need: int, window: int):
        self.need = need
        self.window = window
        self._buf: dict[str, deque] = {}

    def observe(self, zone: str, present: bool) -> bool:
        """Record this sample for the zone and return True if the threshold is now met."""
        dq = self._buf.get(zone)
        if dq is None:
            dq = deque(maxlen=self.window)
            self._buf[zone] = dq
        dq.append(bool(present))
        return sum(dq) >= self.need
