"""ENHANCE: make a low-quality CCTV frame easier for the model to read.

Crop to the exit zone (when known), upscale 2x, and apply CLAHE contrast. Returns new
JPEG bytes for the vision call only; the saved evidence frame stays the original. OpenCV
and numpy are imported lazily, so importing this module never requires them.
"""
from __future__ import annotations


def enhance_jpeg(jpeg_bytes: bytes, zone_box=None, scale=None):
    """Enhance the frame for the model. Returns (jpeg_bytes, transform).

    transform is {"ox", "oy", "scale"} describing how pixel coordinates in the enhanced
    image map back to the original frame (original = offset + enhanced / scale), or None when
    nothing was changed (so the caller knows the model's box is already in original coords).
    """
    from . import config
    scale = config.ENHANCE_SCALE if scale is None else scale
    try:
        import cv2
        import numpy as np
    except Exception:
        return jpeg_bytes, None
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes, None
    h, w = img.shape[:2]
    ox, oy = 0, 0
    if zone_box:
        x, y, bw, bh = (int(round(float(v))) for v in zone_box)
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        bw = max(1, min(bw, w - x))
        bh = max(1, min(bh, h - y))
        img = img[y:y + bh, x:x + bw]
        ox, oy = x, y
    if scale and scale != 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    else:
        scale = 1.0
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    img = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    ok, out = cv2.imencode(".jpg", img)
    if not ok:
        return jpeg_bytes, None
    return out.tobytes(), {"ox": ox, "oy": oy, "scale": float(scale)}


def untransform_box(box, transform):
    """Map a box from enhanced-image coordinates back to original-frame coordinates."""
    if not box or not transform:
        return box
    s = transform["scale"] or 1.0
    return [
        transform["ox"] + float(box[0]) / s,
        transform["oy"] + float(box[1]) / s,
        float(box[2]) / s,
        float(box[3]) / s,
    ]
