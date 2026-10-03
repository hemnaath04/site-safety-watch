"""Sampler tests with a fake capture, so they run with no OpenCV and no video files."""
import os
import tempfile
import unittest

os.environ.setdefault("SSW_DB", os.path.join(tempfile.mkdtemp(prefix="ssw_s_"), "ssw.db"))

from watcher import sampler  # noqa: E402


class FakeCap:
    """Minimal stand in for cv2.VideoCapture."""
    def __init__(self, n_frames, fps=10):
        self.frames = list(range(n_frames))
        self.fps = fps
        self.i = 0
        self.released = False

    def get(self, _prop):
        return self.fps

    def read(self):
        if self.i < len(self.frames):
            f = self.frames[self.i]
            self.i += 1
            return True, f
        return False, None

    def release(self):
        self.released = True


def _encode(frame):
    return f"jpeg:{frame}".encode()


class TestSampling(unittest.TestCase):
    def test_samples_every_interval(self):
        # fps 10, interval 2 -> one sample every 20 frames. 41 frames -> idx 0, 20, 40.
        cap = FakeCap(41, fps=10)
        out = list(sampler.iter_frames(
            "x", interval_sec=2, capture_factory=lambda s: cap, encode=_encode))
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0][1], b"jpeg:0")

    def test_max_frames_caps_output(self):
        cap = FakeCap(200, fps=10)
        out = list(sampler.iter_frames(
            "x", interval_sec=2, max_frames=2,
            capture_factory=lambda s: cap, encode=_encode))
        self.assertEqual(len(out), 2)

    def test_file_mode_stops_at_eof(self):
        cap = FakeCap(5, fps=10)
        out = list(sampler.iter_frames(
            "x", interval_sec=0.1, stream=False,
            capture_factory=lambda s: cap, encode=_encode))
        # does not hang; yields a bounded number and releases the capture
        self.assertTrue(cap.released)
        self.assertGreaterEqual(len(out), 1)

    def test_stream_reconnects_on_drop(self):
        # First capture ends after 20 frames; the stream reconnects to a second capture,
        # reads more, then a failed reopen (factory raises) stops the loop cleanly.
        caps = [FakeCap(20, fps=10), FakeCap(20, fps=10)]
        made = {"n": 0}

        def factory(_s):
            n = made["n"]
            made["n"] += 1
            if n >= len(caps):
                raise RuntimeError("stream gone")
            return caps[n]

        out = list(sampler.iter_frames(
            "x", interval_sec=2, stream=True, reconnect_tries=1,
            capture_factory=factory, encode=_encode))
        # two captures of 20 frames, sample every 20 -> idx 0 from each -> 2 samples,
        # then the third reopen fails and the loop ends without crashing
        self.assertEqual(len(out), 2)
        self.assertGreaterEqual(made["n"], 3)


if __name__ == "__main__":
    unittest.main()
