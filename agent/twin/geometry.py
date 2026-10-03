"""Floor-plan geometry for the twin. numpy, with OpenCV for the homography when present.

Floor coordinates are meters in the room frame from the config (x along width, y along depth).
Pixel coordinates are in the camera's full-resolution frame.
"""

import math

import numpy as np

try:
    import cv2
except ImportError:  # tests and laptops without OpenCV fall back to a numpy DLT
    cv2 = None


def homography(pixels, meters):
    """3x3 matrix mapping pixel (u, v) to floor (x, y). Needs 4+ non-collinear pairs."""
    src = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
    dst = np.asarray(meters, dtype=np.float64).reshape(-1, 2)
    if src.shape[0] < 4 or src.shape != dst.shape:
        raise ValueError("need at least 4 matching pixel and meter points")
    if not (np.isfinite(src).all() and np.isfinite(dst).all()):
        raise ValueError("points must be finite")
    if cv2 is not None:
        h, _ = cv2.findHomography(src, dst, 0)
    else:
        h = _dlt(src, dst)
    if h is None or not np.isfinite(h).all() or abs(np.linalg.det(h)) < 1e-12:
        raise ValueError("degenerate floor points")
    return h / h[2, 2]


def _dlt(src, dst):
    rows = []
    for (u, v), (x, y) in zip(src, dst):
        rows.append([-u, -v, -1, 0, 0, 0, u * x, v * x, x])
        rows.append([0, 0, 0, -u, -v, -1, u * y, v * y, y])
    _, _, vt = np.linalg.svd(np.asarray(rows))
    h = vt[-1].reshape(3, 3)
    return h if abs(h[2, 2]) > 1e-12 else None


def project(h, pts):
    """Apply homography h to Nx2 points. Returns Nx2 float64 (NaN where w is ~0)."""
    p = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    ones = np.ones((p.shape[0], 1))
    q = np.hstack([p, ones]) @ np.asarray(h, dtype=np.float64).T
    w = q[:, 2:3]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = q[:, :2] / w
    out[np.abs(w[:, 0]) < 1e-12] = np.nan
    return out


def feet_point(box):
    """Bottom center of a pixel box [x1, y1, x2, y2]: where a person touches the floor."""
    x1, y1, x2, y2 = (float(v) for v in box)
    return ((x1 + x2) / 2.0, max(y1, y2))


def point_in_polygon(pt, poly) -> bool:
    """Ray casting. Points on an edge may land either way."""
    x, y = float(pt[0]), float(pt[1])
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xc:
                inside = not inside
    return inside


def scale_box_1000(box, width, height):
    """Qwen boxes come on a 0..1000 scale; convert to pixels of a width x height frame."""
    x1, y1, x2, y2 = (float(v) for v in box)
    xs = sorted((x1, x2))
    ys = sorted((y1, y2))
    clamp = lambda v, hi: max(0.0, min(float(hi), v))  # noqa: E731
    return [clamp(xs[0] * width / 1000.0, width), clamp(ys[0] * height / 1000.0, height),
            clamp(xs[1] * width / 1000.0, width), clamp(ys[1] * height / 1000.0, height)]


def footprint(h, box, cam_xy=None, depth_m=None):
    """Estimated floor footprint (4 points in meters) of an object seen in a pixel box.

    The box's bottom edge is taken as the object's front contact line on the floor. A single
    camera cannot see how deep the object is, so the quad is extruded away from the camera by
    depth_m (default: the contact line's length, capped to 0.3..1.2 m). This is an estimate.
    """
    x1, _, x2, y2 = (float(v) for v in box)
    left, right = project(h, [(min(x1, x2), y2), (max(x1, x2), y2)])
    if not (np.isfinite(left).all() and np.isfinite(right).all()):
        return None
    edge = right - left
    length = float(np.hypot(*edge))
    if depth_m is None:
        depth_m = min(1.2, max(0.3, length))
    mid = (left + right) / 2.0
    if cam_xy is not None:
        away = mid - np.asarray(cam_xy, dtype=np.float64)
    else:
        away = np.array([-edge[1], edge[0]])
    norm = float(np.hypot(*away))
    if norm < 1e-9:
        away = np.array([-edge[1], edge[0]])
        norm = float(np.hypot(*away)) or 1.0
    step = away / norm * depth_m
    quad = [left, right, right + step, left + step]
    return [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in quad]


def yaw_vector(yaw_deg):
    r = math.radians(float(yaw_deg))
    return math.cos(r), math.sin(r)
