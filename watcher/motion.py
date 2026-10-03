"""Motion gate: skip the vision call when the scene has not changed.

Keeps the box cheap on an always-on stream. The decision (is_motion) is a pure function
and is unit tested; OpenCV and numpy are imported lazily only to decode and diff frames.
"""
from __future__ import annotations

from . import config


def is_motion(score: float, threshold: float | None = None) -> bool:
    """True if the mean pixel difference is at or above the threshold."""
    threshold = config.MOTION_THRESHOLD if threshold is None else threshold
    return score >= threshold


class MotionGate:
    """Holds the previous small grayscale frame and compares each new one to it."""

    def __init__(self, threshold: float | None = None):
        self.threshold = config.MOTION_THRESHOLD if threshold is None else threshold
        self._prev = None

    def score(self, jpeg_bytes: bytes) -> float:
        import cv2  # lazy
        import numpy as np
        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return float("inf")  # cannot decode: do not gate it out
        small = cv2.resize(img, (64, 64), interpolation=cv2.INTER_AREA)
        if self._prev is None:
            self._prev = small
            return float("inf")  # first frame always passes
        s = float(np.mean(cv2.absdiff(self._prev, small)))
        self._prev = small
        return s

    def passed(self, jpeg_bytes: bytes) -> bool:
        return is_motion(self.score(jpeg_bytes), self.threshold)
