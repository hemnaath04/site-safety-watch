"""Zone lookup. Contract 0.1 says the zone comes from the clip or camera config, not the
model. This maps a clip file name or camera name to a zone so the watcher never guesses.

Rahul names clips NN_hazard_zone.mp4 (for example 01_blocked_exit_exitA.mp4). We read the
zone from that name when it is there, and fall back to this table or a default.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

# Explicit overrides: clip stem or camera name -> zone. Add entries as clips arrive.
CLIP_ZONES = {
    "fake_cam": "exit_a",
}

DEFAULT_ZONE = "exit_a"


def load_zones(path=None) -> dict:
    """Load zones.json, mapping zone -> config (for example {"exit_box": [x,y,w,h]}).

    Returns an empty dict if the file is missing or unreadable, so callers degrade safely.
    """
    path = Path(path or config.ZONES_FILE)
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def exit_box(zone: str, path=None):
    """Return the exit box [x,y,w,h] for a zone from zones.json, or None if unknown."""
    cfg = load_zones(path).get(zone)
    if isinstance(cfg, dict):
        box = cfg.get("exit_box")
        if isinstance(box, (list, tuple)) and len(box) == 4:
            return list(box)
    return None


def resolve_zone(clip_or_cam: str | None, override: str | None = None) -> str:
    """Pick the zone. Priority: explicit override, table, trailing part of the file name."""
    if override:
        return override
    if not clip_or_cam:
        return DEFAULT_ZONE
    stem = Path(clip_or_cam).stem
    if stem in CLIP_ZONES:
        return CLIP_ZONES[stem]
    # NN_hazard_zone -> take the last underscore chunk as the zone, if present.
    parts = stem.split("_")
    if len(parts) >= 3:
        return parts[-1].lower()
    return DEFAULT_ZONE
