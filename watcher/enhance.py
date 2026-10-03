"""ENHANCE: make a low-quality CCTV frame easier for the model to read.

Crop to the exit zone (when known), upscale 2x, and apply CLAHE contrast. Returns new
JPEG bytes for the vision call only; the saved evidence frame stays the original. OpenCV
and numpy are imported lazily, so importing this module never requires them.
"""
from __future__ import annotations


def enhance_jpeg(jpeg_bytes: bytes, zone_box=None, scale: float = 2.0) -> bytes:
    """Return enhanced JPEG bytes. On any failure, return the input unchanged."""
    try:
        import cv2
        import numpy as np
    except Exception:
        return jpeg_bytes
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes
    h, w = img.shape[:2]
    if zone_box:
        x, y, bw, bh = (int(round(float(v))) for v in zone_box)
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        bw = max(1, min(bw, w - x))
        bh = max(1, min(bh, h - y))
        img = img[y:y + bh, x:x + bw]
    if scale and scale != 1.0:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    # CLAHE on the luminance channel.
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    img = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    ok, out = cv2.imencode(".jpg", img)
    return out.tobytes() if ok else jpeg_bytes
