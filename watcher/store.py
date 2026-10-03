"""SQLite event store. Contract 0.2. data/ssw.db is the single source of truth.

A work order is just an event row with status approved. There is no second table.
Raw video never leaves the box; only frame paths and text live here.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY,
  ts TEXT,
  clip TEXT,
  hazard TEXT,
  zone TEXT,
  confidence REAL,
  explanation TEXT,
  frame_path TEXT,
  dedup_key TEXT,
  status TEXT,
  disposition_by TEXT,
  disposition_ts TEXT,
  box TEXT,
  resolved_ts TEXT,
  resolved_frame_path TEXT,
  time_to_clear_sec REAL,
  resolved_announced INTEGER DEFAULT 0
);
"""

_COLUMNS = [
    "id", "ts", "clip", "hazard", "zone", "confidence", "explanation",
    "frame_path", "dedup_key", "status", "disposition_by", "disposition_ts", "box",
    "resolved_ts", "resolved_frame_path", "time_to_clear_sec", "resolved_announced",
]

# Columns added after the first schema; each is nullable so older databases migrate safely.
_ADDED_COLUMNS = {
    "box": "TEXT",
    "resolved_ts": "TEXT",
    "resolved_frame_path": "TEXT",
    "time_to_clear_sec": "REAL",
    "resolved_announced": "INTEGER DEFAULT 0",
}


def _migrate(conn) -> None:
    """Add any newer columns to an older db that predates them."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)")]
    for name, decl in _ADDED_COLUMNS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE events ADD COLUMN {name} {decl}")


def now_iso() -> str:
    # Local time (timezone aware) so the logs and alerts read in the site's clock, even
    # inside a container with no system timezone.
    return config.now_local().isoformat(timespec="seconds")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    _migrate(conn)
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = {k: row[k] for k in _COLUMNS}
    # box is stored as a JSON string; emit it as an array (or None) so the console, the 3D
    # view and the twin get a real list, not a string.
    if d.get("box"):
        try:
            d["box"] = json.loads(d["box"])
        except (ValueError, TypeError):
            d["box"] = None
    return d


def insert_event(conn, *, clip, hazard, zone, confidence, explanation,
                 frame_path, dedup_key, box=None, ts=None) -> dict:
    ts = ts or now_iso()
    box_json = json.dumps(box) if box is not None else None
    cur = conn.execute(
        "INSERT INTO events (ts, clip, hazard, zone, confidence, explanation, "
        "frame_path, dedup_key, status, box) VALUES (?,?,?,?,?,?,?,?, 'new', ?)",
        (ts, clip, hazard, zone, float(confidence), explanation, frame_path,
         dedup_key, box_json),
    )
    conn.commit()
    return get_event(conn, cur.lastrowid)


def get_event(conn, event_id) -> dict | None:
    row = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    return _row_to_dict(row) if row else None


def events_by_status(conn, status) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM events WHERE status = ? ORDER BY id", (status,)
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def mark_posted(conn, event_id) -> dict | None:
    conn.execute("UPDATE events SET status = 'posted' WHERE id = ?", (event_id,))
    conn.commit()
    return get_event(conn, event_id)


def dispose(conn, event_id, status, by) -> dict | None:
    if status not in ("approved", "false_alarm"):
        raise ValueError("status must be approved or false_alarm")
    conn.execute(
        "UPDATE events SET status = ?, disposition_by = ?, disposition_ts = ? WHERE id = ?",
        (status, by, now_iso(), event_id),
    )
    conn.commit()
    return get_event(conn, event_id)


ACTIVE_STATUSES = ("new", "posted", "approved")


def active_events(conn, zone) -> list[dict]:
    """Open hazard events in a zone that could still be resolved."""
    q = ("SELECT * FROM events WHERE zone = ? AND status IN "
         "('new','posted','approved') ORDER BY id")
    return [_row_to_dict(r) for r in conn.execute(q, (zone,)).fetchall()]


def resolve_event(conn, event_id, *, resolved_ts, resolved_frame_path,
                  time_to_clear_sec) -> dict | None:
    """Mark an event resolved with the clear time, a resolution frame and time to clear."""
    conn.execute(
        "UPDATE events SET status = 'resolved', resolved_ts = ?, resolved_frame_path = ?, "
        "time_to_clear_sec = ? WHERE id = ?",
        (resolved_ts, resolved_frame_path, time_to_clear_sec, event_id),
    )
    conn.commit()
    return get_event(conn, event_id)


def pending_resolved(conn) -> list[dict]:
    """Resolved events the agent has not announced yet."""
    rows = conn.execute(
        "SELECT * FROM events WHERE status = 'resolved' AND "
        "COALESCE(resolved_announced, 0) = 0 ORDER BY id"
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def mark_resolved_announced(conn, event_id) -> dict | None:
    conn.execute("UPDATE events SET resolved_announced = 1 WHERE id = ?", (event_id,))
    conn.commit()
    return get_event(conn, event_id)


def recent_with_key(conn, dedup_key, since_iso) -> dict | None:
    """Most recent event with this dedup_key at or after since_iso (for de-duplication)."""
    row = conn.execute(
        "SELECT * FROM events WHERE dedup_key = ? AND ts >= ? ORDER BY ts DESC LIMIT 1",
        (dedup_key, since_iso),
    ).fetchone()
    return _row_to_dict(row) if row else None
