"""Overlap check for LOCATE: how much of the obstruction box sits inside the exit zone.

Pure geometry, fully unit tested. Boxes are [x, y, width, height] in pixels.
"""
from __future__ import annotations


def qwen_xyxy1000_to_xywh(box, width, height):
    """Convert Qwen-VL's native box to pixel [x, y, w, h] of a width x height image.

    Qwen3.6 returns the box as [x1, y1, x2, y2] on a 0..1000 scale regardless of the prompt,
    so we rescale to pixels and turn the corners into an origin plus size. Corners are sorted
    so a flipped box still gives a positive size.
    """
    if not box or len(box) != 4 or not width or not height:
        return box
    x1, y1, x2, y2 = (float(v) for v in box)
    x1, x2 = sorted((x1, x2))
    y1, y2 = sorted((y1, y2))
    px1 = x1 * width / 1000.0
    py1 = y1 * height / 1000.0
    px2 = x2 * width / 1000.0
    py2 = y2 * height / 1000.0
    return [px1, py1, px2 - px1, py2 - py1]


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
