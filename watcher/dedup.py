"""De-duplication. Same hazard and zone inside a time window is one event, not many."""
from __future__ import annotations

from datetime import timedelta

from . import config, store


def make_dedup_key(hazard: str, zone: str, when: datetime, bucket_min: float) -> str:
    """hazard + zone + a coarse time bucket, so repeats inside the window collapse."""
    bucket = int(when.timestamp() // (bucket_min * 60))
    return f"{hazard}:{zone}:{bucket}"


def is_duplicate(conn, hazard: str, zone: str, when: datetime,
                 window_min: float | None = None) -> bool:
    """True if we already stored this hazard and zone inside the recent window."""
    window_min = config.DEDUP_WINDOW_MIN if window_min is None else window_min
    # Keep `since` in the same (local) timezone as the stored timestamps so the string
    # comparison below is chronological.
    since = when - timedelta(minutes=window_min)
    since_iso = since.isoformat(timespec="seconds")
    key = make_dedup_key(hazard, zone, when, window_min)
    if store.recent_with_key(conn, key, since_iso):
        return True
    # also catch the same hazard and zone in the window even across a bucket edge
    rows = [
        e for e in store.events_by_status(conn, "new")
        + store.events_by_status(conn, "posted")
        + store.events_by_status(conn, "approved")
        + store.events_by_status(conn, "false_alarm")
        if e["hazard"] == hazard and e["zone"] == zone and e["ts"] >= since_iso
    ]
    return len(rows) > 0
