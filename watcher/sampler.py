"""Frame sampling from an mp4 file or a live replay stream.

Takes one frame every N seconds and downscales it to about FRAME_WIDTH px wide, then
encodes JPEG bytes for the vision call. The same code reads a file (for the eval) and a
live ffmpeg replay URL (for the demo); pass stream=True so a dropped live stream
reconnects instead of ending.

OpenCV is imported lazily, only for the real capture and the real JPEG encode, so the
sampling and reconnect logic can be unit tested without OpenCV by injecting a fake
capture_factory and encode.
"""
from __future__ import annotations

from datetime import datetime

from . import config

# OpenCV's CAP_PROP_FPS is the stable value 5; hardcode it so the generic loop below
# does not need to import cv2 just for the constant.
_FPS_PROP = 5


def open_capture(source):
    import cv2  # lazy
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open source: {source}")
    return cap


def _default_encode(frame, width):
    import cv2  # lazy
    h, w = frame.shape[:2]
    if w > width:
        scale = width / float(w)
        frame = cv2.resize(frame, (width, int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes() if ok else None


def iter_frames(source, interval_sec=None, width=None, max_frames=None, stream=False,
                reconnect_tries=3, capture_factory=None, encode=None):
    """Yield (clip_seconds, jpeg_bytes) once every interval_sec of video time.

    stream=True keeps reconnecting on a read failure (a live replay), up to
    reconnect_tries times per drop. max_frames caps how many samples are yielded (handy
    for the eval and for a bounded demo capture).
    """
    interval_sec = config.SAMPLE_INTERVAL_SEC if interval_sec is None else interval_sec
    width = config.FRAME_WIDTH if width is None else width
    capture_factory = capture_factory or open_capture
    encode = encode or (lambda f: _default_encode(f, width))

    cap = capture_factory(source)
    fps = cap.get(_FPS_PROP) or 25.0
    step = max(1, int(round(fps * interval_sec)))

    idx = 0
    yielded = 0
    tries_left = reconnect_tries
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                if stream and tries_left > 0:
                    tries_left -= 1
                    cap.release()
                    try:
                        cap = capture_factory(source)
                    except Exception:
                        break  # stream truly gone; stop instead of crashing
                    fps = cap.get(_FPS_PROP) or fps
                    step = max(1, int(round(fps * interval_sec)))
                    continue
                break
            tries_left = reconnect_tries  # reset after a good read
            if idx % step == 0:
                jpeg = encode(frame)
                if jpeg:
                    yield idx / fps, jpeg
                    yielded += 1
                    if max_frames and yielded >= max_frames:
                        break
            idx += 1
    finally:
        cap.release()


def now_local():
    # Timezone-aware local time, consistent with store.now_iso.
    return datetime.now().astimezone()
