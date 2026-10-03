"""Back-project a frame plus relative depth into a colored point cloud. numpy only.

Depth Anything V2 returns relative inverse depth (bigger means closer). We normalize it to
0..1 and use z = 1 / (0.1 + d_norm), so z runs from about 0.91 (closest) to 10 (farthest).
Units are relative, not meters. Intrinsics come from an assumed horizontal field of view.

Axes: x right, y up, z forward (away from the camera), so three.js can use them directly
after negating z if it wants the camera to look down -z.

Wire format from encode():
  uint32 little-endian header length L
  L bytes of UTF-8 JSON header, padded with spaces so 4 + L is a multiple of 4
  count * 3 float32 xyz, then count * 3 uint8 rgb, then count uint8 flag
"""

import json
import math
import struct

import numpy as np

MAX_POINTS = 150_000
Z_OFFSET = 0.1


def _stride_for(h: int, w: int, stride: int, max_points: int) -> int:
    stride = max(1, int(stride))
    while math.ceil(h / stride) * math.ceil(w / stride) > max_points:
        stride += 1
    return stride


def _clip_box(box, h: int, w: int):
    if box is None:
        return None
    try:
        x1, y1, x2, y2 = (int(round(float(v))) for v in box)
    except (TypeError, ValueError):
        return None
    x1, x2 = sorted((max(0, min(w, x1)), max(0, min(w, x2))))
    y1, y2 = sorted((max(0, min(h, y1)), max(0, min(h, y2))))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def backproject(rgb, rel_depth, hfov_deg=70.0, stride=2, box=None, max_points=MAX_POINTS):
    """Return (xyz float32 Nx3, rgb uint8 Nx3, flag uint8 N).

    flag is 1 for pixels inside box = [x1, y1, x2, y2] (pixel coords, end exclusive,
    clipped to the image), else 0. Non-finite depth values are dropped.
    """
    rgb = np.asarray(rgb)
    depth = np.asarray(rel_depth, dtype=np.float64)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must be HxWx3")
    h, w = depth.shape
    if rgb.shape[:2] != (h, w):
        raise ValueError("rgb and depth sizes differ")
    if not 0.0 < hfov_deg < 180.0:
        raise ValueError("hfov_deg must be in (0, 180)")

    stride = _stride_for(h, w, stride, max_points)
    vs = np.arange(0, h, stride)
    us = np.arange(0, w, stride)
    uu, vv = np.meshgrid(us, vs)
    d = depth[vv, uu]
    valid = np.isfinite(d)

    if valid.any():
        lo = d[valid].min()
        hi = d[valid].max()
        span = hi - lo
        d_norm = np.where(valid, (d - lo) / span if span > 0 else 0.0, 0.0)
    else:
        d_norm = np.zeros_like(d)
    z = 1.0 / (Z_OFFSET + d_norm)

    fx = (w / 2.0) / math.tan(math.radians(hfov_deg) / 2.0)
    fy = fx
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    x = (uu - cx) * z / fx
    y = -(vv - cy) * z / fy

    flag = np.zeros(d.shape, dtype=np.uint8)
    clipped = _clip_box(box, h, w)
    if clipped is not None:
        x1, y1, x2, y2 = clipped
        inside = (uu >= x1) & (uu < x2) & (vv >= y1) & (vv < y2)
        flag[inside] = 1

    xyz = np.stack([x[valid], y[valid], z[valid]], axis=1).astype(np.float32)
    colors = rgb[vv, uu][valid].astype(np.uint8)
    return xyz, colors, flag[valid]


def encode(xyz, rgb, flag, meta: dict, hfov_deg: float = 70.0) -> bytes:
    xyz = np.ascontiguousarray(xyz, dtype="<f4").reshape(-1, 3)
    rgb = np.ascontiguousarray(rgb, dtype=np.uint8).reshape(-1, 3)
    flag = np.ascontiguousarray(flag, dtype=np.uint8).reshape(-1)
    count = xyz.shape[0]
    if rgb.shape[0] != count or flag.shape[0] != count:
        raise ValueError("xyz, rgb and flag lengths differ")
    header = dict(meta)
    header.setdefault("hfov_deg", hfov_deg)
    header.update({"count": int(count), "units": "relative"})
    raw = json.dumps(header).encode("utf-8")
    raw += b" " * ((-(4 + len(raw))) % 4)
    return b"".join([struct.pack("<I", len(raw)), raw, xyz.tobytes(), rgb.tobytes(), flag.tobytes()])


def decode(data: bytes):
    """Inverse of encode(). Returns (header dict, xyz, rgb, flag)."""
    (hlen,) = struct.unpack_from("<I", data, 0)
    header = json.loads(data[4:4 + hlen].decode("utf-8"))
    n = int(header["count"])
    off = 4 + hlen
    xyz = np.frombuffer(data, dtype="<f4", count=n * 3, offset=off).reshape(n, 3)
    off += n * 12
    rgb = np.frombuffer(data, dtype=np.uint8, count=n * 3, offset=off).reshape(n, 3)
    off += n * 3
    flag = np.frombuffer(data, dtype=np.uint8, count=n, offset=off)
    return header, xyz, rgb, flag
