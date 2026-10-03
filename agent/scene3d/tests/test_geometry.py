import math
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import geometry  # noqa: E402


def frame(h, w):
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[..., 0] = np.arange(w, dtype=np.uint8)[None, :]
    rgb[..., 1] = np.arange(h, dtype=np.uint8)[:, None]
    return rgb


class BackprojectTest(unittest.TestCase):
    def test_flat_depth_count_and_z(self):
        rgb = frame(4, 4)
        xyz, colors, flag = geometry.backproject(rgb, np.full((4, 4), 0.5), stride=1)
        self.assertEqual(xyz.shape, (16, 3))
        self.assertEqual(xyz.dtype, np.float32)
        self.assertEqual(colors.shape, (16, 3))
        self.assertEqual(flag.shape, (16,))
        # flat depth normalizes to 0, so z = 1 / 0.1 = 10 everywhere
        np.testing.assert_allclose(xyz[:, 2], 10.0, rtol=1e-6)
        self.assertEqual(int(flag.sum()), 0)

    def test_pinhole_from_hfov(self):
        xyz, _, _ = geometry.backproject(frame(4, 4), np.zeros((4, 4)), hfov_deg=90.0, stride=1)
        fx = 2.0 / math.tan(math.radians(45))
        # first pixel (u=0, v=0): x = (0 - 1.5) * 10 / fx, y = +(1.5) * 10 / fx (y up)
        np.testing.assert_allclose(xyz[0], [-1.5 * 10 / fx, 1.5 * 10 / fx, 10.0], rtol=1e-6)

    def test_inverse_depth_closer_is_smaller_z(self):
        d = np.array([[0.0, 1.0]])
        rgb = frame(1, 2)
        xyz, _, _ = geometry.backproject(rgb, d, stride=1)
        np.testing.assert_allclose(xyz[:, 2], [10.0, 1.0 / 1.1], rtol=1e-6)

    def test_box_flags_expected_pixels(self):
        rgb = frame(4, 4)
        _, colors, flag = geometry.backproject(rgb, np.ones((4, 4)), stride=1, box=[1, 1, 3, 3])
        flagged = {(int(c[0]), int(c[1])) for c, f in zip(colors, flag) if f}
        self.assertEqual(flagged, {(1, 1), (2, 1), (1, 2), (2, 2)})

    def test_box_is_clipped_and_bad_box_ignored(self):
        rgb = frame(4, 4)
        _, colors, flag = geometry.backproject(rgb, np.ones((4, 4)), stride=1, box=[2, -5, 99, 1])
        flagged = {(int(c[0]), int(c[1])) for c, f in zip(colors, flag) if f}
        self.assertEqual(flagged, {(2, 0), (3, 0)})
        _, _, flag = geometry.backproject(rgb, np.ones((4, 4)), stride=1, box=[3, 3, 3, 3])
        self.assertEqual(int(flag.sum()), 0)
        _, _, flag = geometry.backproject(rgb, np.ones((4, 4)), stride=1, box=["a", 0, 1, 1])
        self.assertEqual(int(flag.sum()), 0)

    def test_invalid_points_dropped(self):
        d = np.ones((4, 4))
        d[0, 0] = np.nan
        d[3, 3] = np.inf
        xyz, colors, flag = geometry.backproject(frame(4, 4), d, stride=1)
        self.assertEqual(len(xyz), 14)
        self.assertEqual(len(colors), 14)
        self.assertEqual(len(flag), 14)
        self.assertTrue(np.isfinite(xyz).all())

    def test_stride(self):
        xyz, _, _ = geometry.backproject(frame(4, 4), np.ones((4, 4)), stride=2)
        self.assertEqual(len(xyz), 4)
        xyz, _, _ = geometry.backproject(frame(5, 5), np.ones((5, 5)), stride=2)
        self.assertEqual(len(xyz), 9)

    def test_cap_raises_stride(self):
        h, w = 1080, 1920
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        xyz, _, _ = geometry.backproject(rgb, np.ones((h, w), dtype=np.float32), stride=1)
        self.assertLessEqual(len(xyz), geometry.MAX_POINTS)
        # stride 1 and 2 are over the cap (2,073,600 and 518,400); stride 4 gives 129,600
        self.assertEqual(len(xyz), 270 * 480)

    def test_size_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            geometry.backproject(frame(4, 4), np.ones((3, 4)))


class EncodeTest(unittest.TestCase):
    def test_round_trip(self):
        rgb = frame(4, 4)
        xyz, colors, flag = geometry.backproject(rgb, np.random.default_rng(0).random((4, 4)),
                                                 stride=1, box=[0, 0, 2, 2])
        meta = {"event_id": 7, "box": [0, 0, 2, 2], "depth_ms": 12.5}
        data = geometry.encode(xyz, colors, flag, meta)
        header, xyz2, rgb2, flag2 = geometry.decode(data)
        self.assertEqual(header["count"], 16)
        self.assertEqual(header["units"], "relative")
        self.assertEqual(header["hfov_deg"], 70.0)
        self.assertEqual(header["event_id"], 7)
        self.assertEqual(header["box"], [0, 0, 2, 2])
        np.testing.assert_array_equal(xyz2, xyz)
        np.testing.assert_array_equal(rgb2, colors)
        np.testing.assert_array_equal(flag2, flag)
        self.assertEqual(len(data), 4 + int.from_bytes(data[:4], "little") + 16 * (12 + 3 + 1))

    def test_float_block_is_4_byte_aligned(self):
        for key_len in range(6):
            data = geometry.encode(np.zeros((1, 3)), np.zeros((1, 3)), np.zeros(1),
                                   {"k" * (key_len + 1): 1})
            hlen = int.from_bytes(data[:4], "little")
            self.assertEqual((4 + hlen) % 4, 0)

    def test_length_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            geometry.encode(np.zeros((2, 3)), np.zeros((1, 3)), np.zeros(2), {})


if __name__ == "__main__":
    unittest.main()
