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
  box TEXT
);
"""

_COLUMNS = [
    "id", "ts", "clip", "hazard", "zone", "confidence", "explanation",
    "frame_path", "dedup_key", "status", "disposition_by", "disposition_ts", "box",
]


def _migrate(conn) -> None:
    """Add the nullable box column to an older db that predates it."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(events)")]
    if "box" not in cols:
        conn.execute("ALTER TABLE events ADD COLUMN box TEXT")


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


def recent_with_key(conn, dedup_key, since_iso) -> dict | None:
    """Most recent event with this dedup_key at or after since_iso (for de-duplication)."""
    row = conn.execute(
        "SELECT * FROM events WHERE dedup_key = ? AND ts >= ? ORDER BY ts DESC LIMIT 1",
        (dedup_key, since_iso),
    ).fetchone()
    return _row_to_dict(row) if row else None
