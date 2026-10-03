"""Auto-resolution clear-streak tracker.

Counts consecutive clear checks per zone. When the count reaches the threshold, the watcher
resolves the open events in that zone. Pure Python, fully unit tested; the watcher does the
database work and frame saving.
"""
from __future__ import annotations

from . import config


class Resolver:
    def __init__(self, clears_required: int | None = None):
        self.clears_required = (config.CLEARS_TO_RESOLVE if clears_required is None
                                else clears_required)
        self._clear: dict[str, int] = {}

    def observe(self, zone: str, clear: bool) -> bool:
        """Record one sample. Return True when the zone has just reached the clear streak.

        A hazard sample resets the streak. The trigger fires once as the streak is reached;
        further clears keep the count high but there is nothing left to resolve.
        """
        if not clear:
            self._clear[zone] = 0
            return False
        n = self._clear.get(zone, 0) + 1
        self._clear[zone] = n
        return n == self.clears_required
