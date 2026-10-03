"""Tests for the annotated evidence frame."""
import os
import tempfile
import unittest

os.environ.setdefault("SSW_DB", os.path.join(tempfile.mkdtemp(prefix="ssw_an_"), "ssw.db"))

from watcher import annotate  # noqa: E402

try:
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    HAVE_CV = True
except Exception:
    HAVE_CV = False


class TestLabel(unittest.TestCase):
    def test_blocked_exit_label(self):
        self.assertEqual(annotate.label_for("blocked_exit"),
                         "BLOCKED EXIT - 29 CFR 1910.37(a)(3)")

    def test_unknown_label_fallback(self):
        self.assertEqual(annotate.label_for("trip_cable"), "TRIP CABLE")

    def test_label_is_ascii(self):
        # Must render in the OpenCV Hershey font (ASCII only, no em dashes).
        annotate.label_for("blocked_exit").encode("ascii")


class TestAnnotateNoBox(unittest.TestCase):
    def test_no_box_returns_input_unchanged(self):
        self.assertEqual(annotate.annotate_jpeg(b"frame", None, "x"), b"frame")

    def test_empty_bytes_unchanged(self):
        self.assertEqual(annotate.annotate_jpeg(b"", [1, 2, 3, 4], "x"), b"")


@unittest.skipUnless(HAVE_CV, "OpenCV or numpy not installed")
class TestAnnotateDraw(unittest.TestCase):
    def test_draw_changes_pixels_and_stays_jpeg(self):
        import cv2
        import numpy as np
        img = np.full((200, 300, 3), 127, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", img)
        self.assertTrue(ok)
        orig = buf.tobytes()
        out = annotate.annotate_jpeg(orig, [50, 50, 80, 60], "BLOCKED EXIT")
        self.assertIsInstance(out, (bytes, bytearray))
        self.assertNotEqual(out, orig)  # something was drawn
        dec = cv2.imdecode(np.frombuffer(out, np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(dec.shape, img.shape)


if __name__ == "__main__":
    unittest.main()
