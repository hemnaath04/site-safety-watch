"""Slack alert text for one event. Every number here is computed in code."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules import get_rule, title_for  # noqa: E402


def _fmt_time(ts: str | None) -> str:
    if not ts:
        return "unknown"
    try:
        return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts


def _fmt_confidence(value) -> str:
    try:
        return f"{round(float(value) * 100)}%"
    except (TypeError, ValueError):
        return "unknown"


def build_alert(event: dict) -> dict:
    event_id = int(event["id"])
    hazard = event.get("hazard", "")
    rule = get_rule(hazard)
    lines = [
        f"*{title_for(hazard)}*",
        f"Zone: {event.get('zone', 'unknown')}",
        f"Time: {_fmt_time(event.get('ts'))}",
        f"Confidence: {_fmt_confidence(event.get('confidence'))}",
        f"What we saw: {event.get('explanation', '').strip()}",
    ]
    if rule:
        lines.append(f"Rule: {rule['cite']}: {rule['text']}")
        lines.append(f"Fix: {rule['fix']}")
    lines.append(f"Reply `approve {event_id}` or `false-alarm {event_id}`.")
    return {
        "text": "\n".join(lines),
        "event_id": event_id,
        "image_path": event.get("frame_path") or None,
    }
