import json
import math
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np

TWIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TWIN_DIR))
import doors  # noqa: E402
import geometry  # noqa: E402
import tracker  # noqa: E402

PIXELS = [[100, 700], [1100, 700], [900, 300], [300, 300]]
METERS = [[1, 5], [7, 5], [6, 1], [2, 1]]


class GeometryTest(unittest.TestCase):
    def test_homography_round_trip(self):
        h = geometry.homography(PIXELS, METERS)
        np.testing.assert_allclose(geometry.project(h, PIXELS), METERS, atol=1e-6)
        inv = np.linalg.inv(h)
        mid_px = [[600, 500]]
        np.testing.assert_allclose(geometry.project(inv, geometry.project(h, mid_px)), mid_px,
                                   atol=1e-6)

    def test_numpy_fallback_matches(self):
        saved = geometry.cv2
        try:
            geometry.cv2 = None
            h = geometry.homography(PIXELS, METERS)
        finally:
            geometry.cv2 = saved
        np.testing.assert_allclose(geometry.project(h, PIXELS), METERS, atol=1e-6)

    def test_degenerate_points_rejected(self):
        with self.assertRaises(ValueError):
            geometry.homography([[0, 0], [1, 1], [2, 2], [3, 3]], METERS)
        with self.assertRaises(ValueError):
            geometry.homography(PIXELS[:3], METERS[:3])

    def test_feet_point(self):
        self.assertEqual(geometry.feet_point([100, 50, 140, 250]), (120.0, 250.0))

    def test_point_in_polygon(self):
        room = [(0, 0), (8, 0), (8, 6), (0, 6)]
        self.assertTrue(geometry.point_in_polygon((4, 3), room))
        self.assertFalse(geometry.point_in_polygon((9, 3), room))
        self.assertFalse(geometry.point_in_polygon((4, -0.1), room))

    def test_scale_box_1000(self):
        self.assertEqual(geometry.scale_box_1000([500, 250, 250, 1000], 1280, 720),
                         [320.0, 180.0, 640.0, 720.0])

    def test_footprint(self):
        # identity homography: pixels are meters
        h = np.eye(3)
        fp = geometry.footprint(h, [2, 0, 4, 1], cam_xy=(3, 5))
        # bottom edge (2,1)-(4,1) is 2 m long, so depth caps at 1.2 m, extruded away from the
        # camera at (3, 5), which is toward -y
        self.assertEqual(fp, [[2.0, 1.0], [4.0, 1.0], [4.0, -0.2], [2.0, -0.2]])
        short = geometry.footprint(h, [2, 0, 2.1, 1], cam_xy=(2.05, 5))
        self.assertAlmostEqual(short[0][1] - short[3][1], 0.3, places=6)


def fused(*pts):
    return [{"x": x, "y": y, "cams": ["cam1"]} for x, y in pts]


class TrackerTest(unittest.TestCase):
    def test_two_cameras_merge_into_one(self):
        people = tracker.fuse([(2.0, 3.0, "cam1"), (2.3, 3.2, "cam2")])
        self.assertEqual(len(people), 1)
        self.assertAlmostEqual(people[0]["x"], 2.15)
        self.assertAlmostEqual(people[0]["y"], 3.1)
        self.assertEqual(people[0]["cams"], ["cam1", "cam2"])
        tr = tracker.Tracker()
        out = tr.update(people, 0.0)
        self.assertEqual([t["id"] for t in out], [1])

    def test_far_apart_and_same_camera_do_not_merge(self):
        self.assertEqual(len(tracker.fuse([(2.0, 3.0, "cam1"), (3.0, 3.0, "cam2")])), 2)
        self.assertEqual(len(tracker.fuse([(2.0, 3.0, "cam1"), (2.2, 3.0, "cam1")])), 2)

    def test_ids_stable_over_frames(self):
        tr = tracker.Tracker()
        a, b = (1.0, 1.0), (5.0, 4.0)
        first = {t["id"]: (t["x"], t["y"]) for t in tr.update(fused(a, b), 0.0)}
        id_a = next(i for i, p in first.items() if p == a)
        id_b = next(i for i, p in first.items() if p == b)
        for k in range(1, 11):
            t = k * 0.1
            # a walks +x at 1 m/s, b walks -y at 1 m/s; list order flips every frame
            pa = (1.0 + t, 1.0)
            pb = (5.0, 4.0 - t)
            out = tr.update(fused(pb, pa) if k % 2 else fused(pa, pb), t)
            ids = {(round(o["x"], 3), round(o["y"], 3)): o["id"] for o in out}
            self.assertEqual(ids[(round(pa[0], 3), round(pa[1], 3))], id_a)
            self.assertEqual(ids[(round(pb[0], 3), round(pb[1], 3))], id_b)
        track_a = next(o for o in out if o["id"] == id_a)
        self.assertAlmostEqual(track_a["vx"], 1.0, places=2)
        self.assertAlmostEqual(track_a["vy"], 0.0, places=2)

    def test_jump_faster_than_max_speed_is_new_track(self):
        tr = tracker.Tracker()
        tr.update(fused((1.0, 1.0)), 0.0)
        out = tr.update(fused((3.0, 1.0)), 0.1)  # 20 m/s
        self.assertEqual(sorted(o["id"] for o in out), [1, 2])

    def test_track_expiry(self):
        tr = tracker.Tracker()
        tr.update(fused((1.0, 1.0)), 0.0)
        self.assertEqual(len(tr.update([], 1.4)), 1)
        self.assertEqual(tr.update([], 1.6), [])
        out = tr.update(fused((1.0, 1.0)), 1.7)
        self.assertEqual([o["id"] for o in out], [2])


def report(cam, visible=True, open_=False, blocked=False, floor=None):
    return {"cam": cam, "door_visible": visible, "door_open": open_, "blocked": blocked,
            "obstruction_floor": floor}


class DoorMergeTest(unittest.TestCase):
    def test_any_blocked_wins(self):
        m = doors.merge_door([report("cam1"), report("cam2", blocked=True, floor=[[1, 1]] * 4)])
        self.assertTrue(m["blocked"])
        self.assertEqual(m["obstruction_floor"], [[1, 1]] * 4)

    def test_open_needs_strict_majority(self):
        self.assertTrue(doors.merge_door([report("a", open_=True), report("b", open_=True),
                                          report("c")])["open"])
        self.assertFalse(doors.merge_door([report("a", open_=True), report("b")])["open"])

    def test_cameras_that_do_not_see_door_are_ignored(self):
        m = doors.merge_door([report("a", visible=False, blocked=True, open_=True),
                              report("b", open_=False)])
        self.assertFalse(m["blocked"])
        self.assertFalse(m["open"])
        self.assertEqual(m["cams_seeing"], ["b"])
        self.assertIsNone(doors.merge_door([report("a", visible=False)]))
        self.assertIsNone(doors.merge_door([]))

    def test_validate_report(self):
        ok = doors.validate_report({"door_visible": True, "door_open": False, "blocked": True,
                                    "obstruction": [100, 200, 300, 400.4]})
        self.assertEqual(ok["obstruction"], [100, 200, 300, 400])
        self.assertIsNone(doors.validate_report({"door_visible": "yes", "door_open": False,
                                                 "blocked": False, "obstruction": None}))
        self.assertIsNone(doors.validate_report([]))
        flipped = doors.validate_report({"door_visible": True, "door_open": False,
                                         "blocked": True, "obstruction": [300, 200, 100, 400]})
        self.assertIsNone(flipped["obstruction"])


try:
    import cv2  # noqa: F401
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False


class FakeDetector:
    device = "cpu"

    def detect(self, frames):
        return [[([100.0, 300.0, 140.0, 700.0], 0.9)] for _ in frames], 5.0

    def gpu_memory_mb(self):
        return None, None


@unittest.skipUnless(HAVE_CV2, "OpenCV not installed")
class ServerTest(unittest.TestCase):
    def setUp(self):
        import server
        self.server_mod = server
        self.tmp = tempfile.TemporaryDirectory()
        cfg = json.loads((TWIN_DIR / "cameras.example.json").read_text())
        self.cfg_path = Path(self.tmp.name) / "cameras.json"
        self.cfg_path.write_text(json.dumps(cfg))
        self.twin = server.Twin(self.cfg_path, FakeDetector())
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        for cam in self.twin.cameras.values():
            cam.publish(frame)
        server.Handler.twin = self.twin
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.twin.pool.shutdown(wait=False)
        self.tmp.cleanup()

    def req(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data,
                                   method=method)
        if data is not None:
            r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.headers.get("Content-Type"), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type"), e.read()

    def test_config_has_no_paths(self):
        code, _, body = self.req("GET", "/twin/config")
        self.assertEqual(code, 200)
        self.assertNotIn(b"data/clips", body)
        cfg = json.loads(body)
        self.assertEqual([c["id"] for c in cfg["cameras"]], ["cam1", "cam2"])
        self.assertTrue(all(c["calibrated"] for c in cfg["cameras"]))

    def test_config_passes_view_fields_through(self):
        cfg = json.loads(self.req("GET", "/twin/config")[2])
        self.assertEqual(cfg["room"]["top_rotation_deg"], 0)
        self.assertEqual(cfg["room"]["mesh"], {"clip_height_m": 2.2})
        cam1 = cfg["cameras"][0]
        self.assertEqual(cam1["label"], "Phone A, back left")
        self.assertEqual(cam1["sync_group"], "exit_demo")
        self.assertEqual(cam1["pose"], {"x": 0.5, "y": 5.5, "yaw_deg": -40.0, "z": 1.6,
                                        "look_at": [4, 0, 1], "hfov_deg": 70})

    def test_state_reports_sync_groups(self):
        state = json.loads(self.req("GET", "/twin/state")[2])
        self.assertIn("exit_demo", state["sync"])
        group = self.twin.groups["exit_demo"]
        self.assertEqual(group.offsets, {"cam1": 0.0, "cam2": 3.5})
        group.register("cam1", 60.0)
        group.register("cam2", 58.0)
        sync = json.loads(self.req("GET", "/twin/state")[2])["sync"]["exit_demo"]
        self.assertEqual(sync["loop_len"], 54.5)
        self.assertGreaterEqual(sync["t"], 0.0)
        self.assertLess(sync["t"], 54.5)

    def test_detect_once_then_state(self):
        self.twin.detect_once()
        code, _, body = self.req("GET", "/twin/state")
        self.assertEqual(code, 200)
        state = json.loads(body)
        self.assertEqual({c["id"] for c in state["cameras"]}, {"cam1", "cam2"})
        self.assertTrue(all(c["people_in_view"] == 1 for c in state["cameras"]))
        self.assertTrue(state["people"])
        for p in state["people"]:
            self.assertEqual(set(p), {"id", "x", "y", "vx", "vy", "cams"})
        self.assertEqual(state["doors"][0]["id"], "exit_a")
        stats = json.loads(self.req("GET", "/twin/stats")[2])
        self.assertEqual(stats["detector"]["batch_ms_p50"], 5.0)
        self.assertEqual(stats["detector"]["batches"], 1)

    def test_door_merge_into_state(self):
        def fake_ask(cam):
            return {"cam": cam.id, "door_id": cam.door_id, "door_visible": True,
                    "door_open": False, "blocked": cam.id == "cam2",
                    "obstruction_floor": [[3, 0.5], [4, 0.5], [4, 0], [3, 0]]
                    if cam.id == "cam2" else None}
        self.twin._ask_door = fake_ask
        self.twin.doors_once()
        door = json.loads(self.req("GET", "/twin/state")[2])["doors"][0]
        self.assertTrue(door["blocked"])
        self.assertFalse(door["open"])
        self.assertEqual(door["obstruction_floor"][0], [3, 0.5])
        self.assertIsNotNone(door["updated"])

    def test_camera_jpeg(self):
        code, ctype, body = self.req("GET", "/twin/camera/cam1.jpg")
        self.assertEqual((code, ctype), (200, "image/jpeg"))
        self.assertTrue(body.startswith(b"\xff\xd8"))
        self.assertEqual(self.req("GET", "/twin/camera/nope.jpg")[0], 404)
        self.assertEqual(self.req("GET", "/twin/camera/bad%20id.jpg")[0], 400)

    def test_health_and_unknown_route(self):
        code, _, body = self.req("GET", "/twin/health")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])
        self.assertEqual(self.req("GET", "/nope")[0], 404)

    def test_calibrate_page_and_save(self):
        code, ctype, _ = self.req("GET", "/twin/calibrate/cam1")
        self.assertEqual(code, 200)
        self.assertTrue(ctype.startswith("text/html"))
        info = json.loads(self.req("GET", "/twin/calibrate/cam1?format=json")[2])
        self.assertEqual(info["frame_w"], 1280)
        new = {"pixels": PIXELS, "meters": METERS}
        code, _, body = self.req("POST", "/twin/calibrate/cam1", new)
        self.assertEqual(code, 200, body)
        saved = json.loads(self.cfg_path.read_text())
        self.assertEqual(saved["cameras"][0]["floor_points"]["pixels"],
                         [[float(u), float(v)] for u, v in PIXELS])
        bak = json.loads(Path(str(self.cfg_path) + ".bak").read_text())
        self.assertNotEqual(bak["cameras"][0]["floor_points"]["pixels"],
                            saved["cameras"][0]["floor_points"]["pixels"])
        np.testing.assert_allclose(
            geometry.project(self.twin.cameras["cam1"].H, PIXELS), METERS, atol=1e-6)

    def test_calibrate_bad_input(self):
        p = "/twin/calibrate/cam1"
        self.assertEqual(self.req("POST", p, {"pixels": PIXELS[:3], "meters": METERS[:3]})[0], 400)
        self.assertEqual(self.req("POST", p, {"pixels": [[0, 0], [1, 1], [2, 2], [3, 3]],
                                              "meters": METERS})[0], 400)
        self.assertEqual(self.req("POST", p, {"pixels": PIXELS,
                                              "meters": [[1, "a"]] * 4})[0], 400)
        self.assertEqual(self.req("POST", "/twin/calibrate/nope",
                                  {"pixels": PIXELS, "meters": METERS})[0], 404)
        self.assertFalse(Path(str(self.cfg_path) + ".bak").exists())


if __name__ == "__main__":
    unittest.main()
