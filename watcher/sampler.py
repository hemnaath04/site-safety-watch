"""Frame sampling from an mp4 or a replay stream.

Takes one frame every N seconds and downscales it to about FRAME_WIDTH px wide, then
encodes JPEG bytes for the vision call. OpenCV is only needed where frames are read
(the box, or a laptop with clips); the store, rules, dedup and CLI do not import this.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import config


def _downscale(frame, width):
    import cv2  # local import so the rest of the package runs without OpenCV
    h, w = frame.shape[:2]
    if w <= width:
        return frame
    scale = width / float(w)
    return cv2.resize(frame, (width, int(h * scale)), interpolation=cv2.INTER_AREA)


def iter_frames(source, interval_sec=None, width=None):
    """Yield (clip_seconds, jpeg_bytes) once every interval_sec of video time.

    source is an mp4 path or a stream URL. Works for a file or a live replay.
    """
    import cv2
    interval_sec = config.SAMPLE_INTERVAL_SEC if interval_sec is None else interval_sec
    width = config.FRAME_WIDTH if width is None else width

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open source: {source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(fps * interval_sec)))

    idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % step == 0:
                small = _downscale(frame, width)
                ok2, buf = cv2.imencode(".jpg", small)
                if ok2:
                    yield idx / fps, buf.tobytes()
            idx += 1
    finally:
        cap.release()


def utc_now():
    return datetime.now(timezone.utc)
