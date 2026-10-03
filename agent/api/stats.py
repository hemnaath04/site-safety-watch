"""Counts, timings, digest and escalation text from event rows. Pure code, no model.

Timestamps are ISO 8601. A timestamp without an offset is read as UTC.
"""

import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules import title_for  # noqa: E402

STATUSES = ("new", "posted", "approved", "false_alarm")
OPEN = ("new", "posted")
DECIDED = ("approved", "false_alarm")
MAX_OPEN_IDS_IN_DIGEST = 10


def parse_ts(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60.0


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def window(now: datetime, hours: float):
    return now - timedelta(hours=hours), now


def compute_stats(events, start: datetime, end: datetime) -> dict:
    """Stats for events whose ts falls in [start, end]. Open means new or posted."""
    in_window = []
    for ev in events:
        ts = parse_ts(ev.get("ts"))
        if ts is not None and start <= ts <= end:
            in_window.append((ev, ts))
    in_window.sort(key=lambda pair: (pair[1], pair[0].get("id", 0)))

    by_status = {s: 0 for s in STATUSES}
    by_zone = {}
    open_ids = []
    decision_minutes = []
    open_minutes = []
    for ev, ts in in_window:
        status = ev.get("status")
        if status in by_status:
            by_status[status] += 1
        zone = by_zone.setdefault(ev.get("zone") or "unknown",
                                  {"total": 0, "open": 0, "approved": 0, "false_alarm": 0})
        zone["total"] += 1
        if status in OPEN:
            zone["open"] += 1
            open_ids.append(ev.get("id"))
            open_minutes.append(_minutes(end - ts))
        elif status in DECIDED:
            zone[status] += 1
            decided = parse_ts(ev.get("disposition_ts"))
            if decided is not None and decided >= ts:
                decision_minutes.append(_minutes(decided - ts))

    return {
        "window": {"from": _iso(start), "to": _iso(end),
                   "hours": round((end - start).total_seconds() / 3600.0, 2)},
        "total": len(in_window),
        "by_status": by_status,
        "by_zone": dict(sorted(by_zone.items())),
        "open_event_ids": open_ids,
        "median_minutes_to_decision":
            round(statistics.median(decision_minutes), 1) if decision_minutes else None,
        "longest_open_minutes": round(max(open_minutes), 1) if open_minutes else None,
    }


def _hours_label(stats: dict) -> str:
    hours = stats["window"].get("hours")
    if hours is None:
        start = parse_ts(stats["window"]["from"])
        end = parse_ts(stats["window"]["to"])
        hours = (end - start).total_seconds() / 3600.0
    return f"{hours:g}"


def digest_text(stats: dict) -> str:
    """Slack mrkdwn, at most 8 lines."""
    n = _hours_label(stats)
    if not stats["total"]:
        return f"No hazards in the last {n} h."
    s = stats["by_status"]
    lines = [
        f"*Site Safety Watch: last {n} h*",
        f"{stats['total']} hazards: {s['new']} new, {s['posted']} posted, "
        f"{s['approved']} approved, {s['false_alarm']} false alarm.",
        "By zone: " + ", ".join(
            f"{zone} {z['total']} ({z['open']} open, {z['approved']} approved, "
            f"{z['false_alarm']} false alarm)"
            for zone, z in stats["by_zone"].items()),
    ]
    median = stats["median_minutes_to_decision"]
    lines.append("Median time to decision: "
                 + (f"{median} min." if median is not None else "no decisions yet."))
    ids = stats["open_event_ids"]
    if ids:
        shown = ", ".join(f"#{i}" for i in ids[:MAX_OPEN_IDS_IN_DIGEST])
        more = len(ids) - MAX_OPEN_IDS_IN_DIGEST
        lines.append(f"Open: {shown}" + (f" and {more} more." if more > 0 else "."))
        lines.append(f"Longest open: {stats['longest_open_minutes']} min.")
    else:
        lines.append("Open: none.")
    return "\n".join(lines)


def minutes_waiting(event: dict, now: datetime):
    """Whole minutes since the event was first seen, or None if ts does not parse."""
    ts = parse_ts(event.get("ts"))
    return None if ts is None else int(_minutes(now - ts))


def escalations(events, now: datetime, after_min: float) -> list:
    """Posted events first seen more than after_min minutes ago with no decision, oldest first."""
    out = []
    for ev in events:
        if ev.get("status") != "posted" or ev.get("disposition_ts"):
            continue
        ts = parse_ts(ev.get("ts"))
        if ts is not None and _minutes(now - ts) > after_min:
            out.append((ts, ev))
    out.sort(key=lambda pair: pair[0])
    return [ev for _, ev in out]


def escalation_text(event: dict, minutes: int) -> str:
    eid = int(event["id"])
    return (f"Escalation: event {eid} ({title_for(event.get('hazard', ''))}, "
            f"{event.get('zone', 'unknown')}) has had no decision for {int(minutes)} min. "
            f"Reply `approve {eid}` or `false-alarm {eid}`.")
