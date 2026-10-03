"""SQLite event store. Contract 0.2. data/ssw.db is the single source of truth.

A work order is just an event row with status approved. There is no second table.
Raw video never leaves the box; only frame paths and text live here.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
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
  disposition_ts TEXT
);
"""

_COLUMNS = [
    "id", "ts", "clip", "hazard", "zone", "confidence", "explanation",
    "frame_path", "dedup_key", "status", "disposition_by", "disposition_ts",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = Path(db_path or config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {k: row[k] for k in _COLUMNS}


def insert_event(conn, *, clip, hazard, zone, confidence, explanation,
                 frame_path, dedup_key, ts=None) -> dict:
    ts = ts or now_iso()
    cur = conn.execute(
        "INSERT INTO events (ts, clip, hazard, zone, confidence, explanation, "
        "frame_path, dedup_key, status) VALUES (?,?,?,?,?,?,?,?, 'new')",
        (ts, clip, hazard, zone, float(confidence), explanation, frame_path, dedup_key),
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


def recent_with_key(conn, dedup_key, since_iso) -> dict | None:
    """Most recent event with this dedup_key at or after since_iso (for de-duplication)."""
    row = conn.execute(
        "SELECT * FROM events WHERE dedup_key = ? AND ts >= ? ORDER BY ts DESC LIMIT 1",
        (dedup_key, since_iso),
    ).fetchone()
    return _row_to_dict(row) if row else None
