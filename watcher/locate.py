"""Overlap check for LOCATE: how much of the obstruction box sits inside the exit zone.

Pure geometry, fully unit tested. Boxes are [x, y, width, height] in pixels.
"""
from __future__ import annotations


def _area(box) -> float:
    return max(0.0, float(box[2])) * max(0.0, float(box[3]))


def overlap_fraction(obstruction, zone_box) -> float:
    """Fraction of the obstruction box area that falls inside the zone box (0.0 to 1.0)."""
    if not obstruction or not zone_box:
        return 0.0
    ax, ay, aw, ah = (float(v) for v in obstruction)
    zx, zy, zw, zh = (float(v) for v in zone_box)
    ix = max(ax, zx)
    iy = max(ay, zy)
    ix2 = min(ax + aw, zx + zw)
    iy2 = min(ay + ah, zy + zh)
    inter = max(0.0, ix2 - ix) * max(0.0, iy2 - iy)
    area = _area(obstruction)
    return inter / area if area > 0 else 0.0


def in_zone(obstruction, zone_box, min_overlap: float) -> bool:
    """True if the obstruction overlaps the exit zone by at least min_overlap."""
    return overlap_fraction(obstruction, zone_box) >= min_overlap
