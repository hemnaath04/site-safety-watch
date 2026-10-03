"""Tests for the stretch features: motion gate, second look, face blur.

Pure logic is always tested. The parts that need OpenCV or numpy skip cleanly where those
are not installed (they run on the box, which has both).
"""
import os
import tempfile
import unittest

os.environ.setdefault("SSW_DB", os.path.join(tempfile.mkdtemp(prefix="ssw_x_"), "ssw.db"))

from watcher import blur, motion, store, vision  # noqa: E402
from watcher import watcher as watcher_mod  # noqa: E402

try:
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    HAVE_CV = True
except Exception:
    HAVE_CV = False


def _noop_log(_msg):
    pass


class TestMotionPure(unittest.TestCase):
    def test_is_motion_above_threshold(self):
        self.assertTrue(motion.is_motion(5.0, threshold=3.0))

    def test_is_motion_at_threshold(self):
        self.assertTrue(motion.is_motion(3.0, threshold=3.0))

    def test_no_motion_below_threshold(self):
        self.assertFalse(motion.is_motion(1.0, threshold=3.0))


class TestSecondLook(unittest.TestCase):
    def setUp(self):
        self.conn = store.connect()
        self.conn.execute("DELETE FROM events")
        self.conn.commit()

    def test_confirmed_candidate_is_stored(self):
        client = vision.FakeVision(script=["blocked_exit", "blocked_exit"])
        row = watcher_mod._handle(self.conn, client, None, "c", "zc_conf", _noop_log,
                                  second_look=True, do_blur=False)
        self.assertIsNotNone(row)
        self.assertEqual(row["hazard"], "blocked_exit")

    def test_false_alarm_is_filtered(self):
        client = vision.FakeVision(script=["blocked_exit", "none"])
        row = watcher_mod._handle(self.conn, client, None, "c", "zc_false", _noop_log,
                                  second_look=True, do_blur=False)
        self.assertIsNone(row)

    def test_without_second_look_candidate_is_stored(self):
        client = vision.FakeVision(script=["blocked_exit", "none"])
        row = watcher_mod._handle(self.conn, client, None, "c", "zc_nolook", _noop_log,
                                  second_look=False, do_blur=False)
        self.assertIsNotNone(row)


@unittest.skipUnless(HAVE_CV, "OpenCV or numpy not installed")
class TestMotionGateCv(unittest.TestCase):
    def test_first_frame_passes_then_static_is_gated(self):
        import cv2
        import numpy as np
        black = np.zeros((120, 160, 3), dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", black)
        self.assertTrue(ok)
        jpeg = buf.tobytes()
        gate = motion.MotionGate(threshold=3.0)
        self.assertTrue(gate.passed(jpeg))      # first frame always passes
        self.assertFalse(gate.passed(jpeg))     # identical frame, no motion


@unittest.skipUnless(HAVE_CV, "OpenCV or numpy not installed")
class TestBlurCv(unittest.TestCase):
    def test_blur_is_noop_without_a_face(self):
        import cv2
        import numpy as np
        img = np.full((80, 80, 3), 127, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", img)
        self.assertTrue(ok)
        out = blur.blur_jpeg(buf.tobytes())
        self.assertIsInstance(out, (bytes, bytearray))
        # still a decodable JPEG of the same shape
        arr = np.frombuffer(out, dtype=np.uint8)
        dec = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        self.assertEqual(dec.shape, img.shape)


if __name__ == "__main__":
    unittest.main()
