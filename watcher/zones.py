"""Zone lookup. Contract 0.1 says the zone comes from the clip or camera config, not the
model. This maps a clip file name or camera name to a zone so the watcher never guesses.

Rahul names clips NN_hazard_zone.mp4 (for example 01_blocked_exit_exitA.mp4). We read the
zone from that name when it is there, and fall back to this table or a default.
"""
from __future__ import annotations

from pathlib import Path

# Explicit overrides: clip stem or camera name -> zone. Add entries as clips arrive.
CLIP_ZONES = {
    "fake_cam": "exit_a",
}

DEFAULT_ZONE = "exit_a"


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
