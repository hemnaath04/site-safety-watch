"""Face blur for the saved evidence frame.

A hard team rule: a frame that could show a person must be blurred before it is posted.
We blur any detected face and leave the rest of the frame (the blocked exit) intact. If no
face is found it is a no-op. OpenCV and numpy are imported lazily.

If the face cascade cannot load we raise, rather than risk posting an unblurred face. Run
with the blur turned off only on clips that provably contain no people.
"""
from __future__ import annotations

_cascade = None


def _get_cascade():
    import cv2  # lazy
    global _cascade
    if _cascade is None:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        c = cv2.CascadeClassifier(path)
        if c.empty():
            raise RuntimeError(
                "face cascade failed to load; install opencv data or run with --no-blur "
                "on clips that contain no people")
        _cascade = c
    return _cascade


def blur_jpeg(jpeg_bytes: bytes) -> bytes:
    """Return JPEG bytes with any detected face blurred. No-op if no face is found."""
    import cv2  # lazy
    import numpy as np
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = _get_cascade().detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    for (x, y, w, h) in faces:
        roi = img[y:y + h, x:x + w]
        img[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (0, 0), sigmaX=12)
    ok, out = cv2.imencode(".jpg", img)
    return out.tobytes() if ok else jpeg_bytes
