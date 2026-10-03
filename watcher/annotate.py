"""Draw the obstruction box and a label on an evidence frame.

Runs after the face blur, so the drawn frame is already privacy safe. Draws nothing when
there is no box (a clear or resolution frame stays plain). OpenCV is imported lazily; on any
failure the frame is returned unchanged.
"""
from __future__ import annotations

# Label per hazard. ASCII only so the OpenCV Hershey font renders it (no em dashes).
LABELS = {
    "blocked_exit": "BLOCKED EXIT - 29 CFR 1910.37(a)(3)",
}


def label_for(hazard: str) -> str:
    return LABELS.get(hazard, (hazard or "").replace("_", " ").upper())


def annotate_jpeg(jpeg_bytes: bytes, box, label: str) -> bytes:
    """Return JPEG bytes with the box and label drawn. No box means no change."""
    if not box or not jpeg_bytes:
        return jpeg_bytes
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
    x, y, bw, bh = (int(round(float(v))) for v in box)
    x = max(0, min(x, w - 1))
    y = max(0, min(y, h - 1))
    bw = max(1, min(bw, w - x))
    bh = max(1, min(bh, h - y))
    red = (0, 0, 255)
    cv2.rectangle(img, (x, y), (x + bw, y + bh), red, 3)

    # Label chip above the box (or just below the top edge if there is no room).
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.5, min(1.0, w / 1200.0))
    thick = max(1, int(round(scale * 2)))
    (tw, th), base = cv2.getTextSize(label, font, scale, thick)
    ty = y - 8 if y - 8 - th > 0 else y + bh + th + 8
    rect_y1 = ty - th - base
    cv2.rectangle(img, (x, rect_y1), (x + tw + 8, ty + base), red, -1)
    cv2.putText(img, label, (x + 4, ty), font, scale, (255, 255, 255), thick,
                cv2.LINE_AA)

    ok, out = cv2.imencode(".jpg", img)
    return out.tobytes() if ok else jpeg_bytes
