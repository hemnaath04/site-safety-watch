import importlib.util
import json
import os
import socket
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

VIEWER_DIR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ssw_viewer", VIEWER_DIR / "serve.py")
viewer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(viewer)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class StubApiHandler(BaseHTTPRequestHandler):
    frame_path = ""

    def log_message(self, _fmt, *_args):
        pass

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True})
        elif self.path.startswith("/events/1"):
            self._json(200, {
                "id": 1,
                "ts": "2026-10-03T12:05:00",
                "hazard": "blocked_exit",
                "zone": "exit_a",
                "confidence": 0.91,
                "explanation": "Boxes block the exit.",
                "frame_path": self.frame_path,
                "status": "new",
                "rule": "29 CFR 1910.37: Exit routes must be free and unobstructed.",
                "fix": "Move the obstruction out of the exit route and tag the zone.",
            })
        elif self.path.startswith("/events"):
            self._json(200, [])
        else:
            self._json(404, {"error": "not found"})

    def _json(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def scene_payload():
    header = json.dumps({
        "count": 2,
        "hfov_deg": 70,
        "units": "relative",
        "depth_ms": 42.5,
        "box": [0.1, 0.2, 0.8, 0.9],
    }, separators=(",", ":")).encode()
    xyz = struct.pack("<6f", 0.0, 0.0, 0.0, 1.0, 0.5, -0.5)
    rgb = bytes([12, 34, 56, 180, 160, 140])
    flags = bytes([0, 1])
    return struct.pack("<I", len(header)) + header + xyz + rgb + flags


class StubSceneHandler(BaseHTTPRequestHandler):
    payload = scene_payload()

    def log_message(self, _fmt, *_args):
        pass

    def do_GET(self):
        if self.path in ("/scene/live", "/scene/event/1"):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(self.payload)))
            self.end_headers()
            self.wfile.write(self.payload)
        else:
            self.send_error(404)


class ViewerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "frames").mkdir()
        self.frame = self.root / "frames" / "event_1.jpg"
        self.frame.write_bytes(b"fake-jpeg-data")
        StubApiHandler.frame_path = "frames/event_1.jpg"

        self.api_port = free_port()
        self.api = ThreadingHTTPServer(("127.0.0.1", self.api_port), StubApiHandler)
        self.api_thread = threading.Thread(target=self.api.serve_forever, daemon=True)
        self.api_thread.start()

        self.scene_port = free_port()
        self.scene = ThreadingHTTPServer(("127.0.0.1", self.scene_port), StubSceneHandler)
        self.scene_thread = threading.Thread(target=self.scene.serve_forever, daemon=True)
        self.scene_thread.start()

        self.viewer_port = free_port()
        self.env = patch.dict(os.environ, {
            "SSW_API_URL": f"http://127.0.0.1:{self.api_port}",
            "SSW_FRAMES_ROOT": str(self.root),
            "SCENE_URL": f"http://127.0.0.1:{self.scene_port}",
        })
        self.env.start()
        self.repo_root = patch.object(viewer, "REPO_ROOT", self.root)
        self.repo_root.start()
        self.server = viewer.make_server("127.0.0.1", self.viewer_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.api.shutdown()
        self.api.server_close()
        self.scene.shutdown()
        self.scene.server_close()
        self.repo_root.stop()
        self.env.stop()
        self.tmp.cleanup()

    def request(self, path):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.viewer_port}{path}", timeout=5) as response:
                return response.status, response.headers.get_content_type(), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get_content_type(), exc.read()

    def test_static_files(self):
        status, content_type, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "text/html")
        self.assertIn(b"Site Safety Watch", body)
        self.assertEqual(self.request("/app.css")[:2], (200, "text/css"))
        self.assertEqual(self.request("/app.js")[:2], (200, "text/javascript"))

    def test_api_proxy(self):
        status, content_type, body = self.request("/api/health")
        self.assertEqual((status, content_type), (200, "application/json"))
        self.assertEqual(json.loads(body), {"ok": True})

    def test_scene_proxy_preserves_binary(self):
        status, content_type, body = self.request("/scene3d/scene/live")
        self.assertEqual((status, content_type), (200, "application/octet-stream"))
        self.assertEqual(body, StubSceneHandler.payload)
        header_length = struct.unpack_from("<I", body, 0)[0]
        header = json.loads(body[4:4 + header_length])
        self.assertEqual(header["count"], 2)
        self.assertEqual(header["units"], "relative")

    def test_frame_is_served_inside_root(self):
        status, content_type, body = self.request("/frames/1")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(body, b"fake-jpeg-data")

    def test_frame_path_traversal_is_refused(self):
        status, _content_type, _body = self.request("/frames/%2e%2e/%2e%2e/etc/passwd")
        self.assertEqual(status, 404)

    def test_numbers_is_404_when_absent(self):
        status, _content_type, _body = self.request("/numbers")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
