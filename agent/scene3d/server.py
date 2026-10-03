"""3D scene service: depth on the GB10 GPU, returned as a compact point cloud.

Runs inside the vLLM image (torch, transformers, opencv, numpy, Pillow already present).
Env: SCENE_HOST (127.0.0.1), SCENE_PORT (8300), SSW_API_URL (http://172.18.0.1:8100),
SSW_REPO_ROOT (/repo), SSW_DEMO_CLIP (unset disables /scene/live), SCENE_MODEL_DIR
(/models/Depth-Anything-V2-Small-hf), SCENE_HFOV_DEG (70, an assumption).
"""

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
import geometry  # noqa: E402

MODEL_NAME = "Depth-Anything-V2-Small-hf"
MODEL_DIR = os.environ.get("SCENE_MODEL_DIR", f"/models/{MODEL_NAME}")
SSW_API_URL = os.environ.get("SSW_API_URL", "http://172.18.0.1:8100").rstrip("/")
REPO_ROOT = Path(os.environ.get("SSW_REPO_ROOT", "/repo")).resolve()
DEMO_CLIP = os.environ.get("SSW_DEMO_CLIP") or None
HFOV_DEG = float(os.environ.get("SCENE_HFOV_DEG", "70"))
STRIDE = int(os.environ.get("SCENE_STRIDE", "2"))
ID_RE = re.compile(r"^[0-9]{1,18}$")


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class DepthModel:
    """Loads once; calls are serialized because one GPU model is shared by all threads."""

    def __init__(self, model_dir: str):
        import torch
        # On the GB10 (sm_121) this torch build's cuDNN has no engine for these fp16 convs
        # ("unable to find an engine"); the native CUDA path works: 13.6 ms per 518x784 frame
        # in fp16 measured on the box.
        torch.backends.cudnn.enabled = False
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.processor = AutoImageProcessor.from_pretrained(model_dir)
        self.model = AutoModelForDepthEstimation.from_pretrained(
            model_dir, dtype=self.dtype).to(self.device).eval()
        self.lock = threading.Lock()

    def _sync(self):
        if self.device == "cuda":
            self.torch.cuda.synchronize()

    def __call__(self, rgb):
        """rgb HxWx3 uint8 -> (relative inverse depth HxW float32, depth_ms)."""
        from PIL import Image

        torch = self.torch
        h, w = rgb.shape[:2]
        inputs = self.processor(images=Image.fromarray(rgb), return_tensors="pt")
        pixel_values = inputs["pixel_values"].to(self.device, dtype=self.dtype)
        with self.lock, torch.inference_mode():
            self._sync()
            t0 = time.perf_counter()
            pred = self.model(pixel_values=pixel_values).predicted_depth
            pred = torch.nn.functional.interpolate(
                pred.unsqueeze(1).float(), size=(h, w), mode="bicubic", align_corners=False)
            self._sync()
            depth_ms = (time.perf_counter() - t0) * 1000.0
        return pred[0, 0].cpu().numpy(), depth_ms


class LiveClip:
    """Frame of the demo clip at the current wall-clock position, looping."""

    def __init__(self, path: str):
        import cv2

        self.cv2 = cv2
        self.path = path
        self.lock = threading.Lock()
        self.cap = None
        self.fps = 0.0
        self.frames = 0

    def _open(self):
        cap = self.cv2.VideoCapture(self.path)
        if not cap.isOpened():
            raise HttpError(502, "cannot open demo clip")
        self.cap = cap
        self.fps = cap.get(self.cv2.CAP_PROP_FPS) or 0.0
        self.frames = int(cap.get(self.cv2.CAP_PROP_FRAME_COUNT) or 0)
        if self.fps <= 0 or self.frames <= 0:
            raise HttpError(502, "demo clip has no frame count")

    def read(self):
        cv2 = self.cv2
        with self.lock:
            if self.cap is None:
                self._open()
            duration = self.frames / self.fps
            t_sec = time.time() % duration
            idx = min(self.frames - 1, int(t_sec * self.fps))
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, bgr = self.cap.read()
            if not ok:
                self.cap.release()
                self.cap = None
                raise HttpError(502, "cannot read demo clip frame")
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), round(t_sec, 3)


def parse_box(value):
    """Accept [x1, y1, x2, y2] as a list or 'x1,y1,x2,y2'. Return a list of 4 ints or None."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.split(",")
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return [int(round(float(v))) for v in value]
    except (TypeError, ValueError):
        return None


def fetch_event(event_id: str) -> dict:
    url = f"{SSW_API_URL}/events/{event_id}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise HttpError(404, "event not found")
        raise HttpError(502, f"event api returned {exc.code}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        raise HttpError(502, "event api unreachable")


def safe_frame_path(frame_path) -> Path:
    if not isinstance(frame_path, str) or not frame_path:
        raise HttpError(404, "event has no frame")
    path = (REPO_ROOT / frame_path).resolve()
    if not path.is_relative_to(REPO_ROOT):
        raise HttpError(400, "frame path outside repo root")
    if not path.is_file():
        raise HttpError(404, "frame file missing")
    return path


def load_rgb(path: Path):
    import numpy as np
    from PIL import Image

    with Image.open(path) as img:
        return np.asarray(img.convert("RGB"))


class Handler(BaseHTTPRequestHandler):
    server_version = "scene3d/1"
    model: DepthModel = None
    live: LiveClip = None
    live_ema = None  # time-smoothed depth for /scene/live, so the cloud does not shimmer

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.log_date_time_string()} {fmt % args}\n")

    def _json(self, status: int, body: dict):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _binary(self, payload: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        t0 = time.perf_counter()
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        query = parse_qs(url.query)
        try:
            if parts == ["health"]:
                self._json(200, {"ok": True, "device": self.model.device, "model": MODEL_NAME})
            elif len(parts) == 3 and parts[:2] == ["scene", "event"]:
                self._scene_event(parts[2], query, t0)
            elif parts == ["scene", "live"]:
                self._scene_live(t0)
            else:
                self._json(404, {"error": "no such route"})
        except HttpError as exc:
            self._json(exc.status, {"error": exc.message})
        except Exception as exc:  # last resort: never leak a traceback to the client
            sys.stderr.write(f"internal error: {exc!r}\n")
            self._json(500, {"error": "internal error"})

    def _render(self, rgb, box, meta: dict, t0: float, smooth: bool = False) -> bytes:
        rel_depth, depth_ms = self.model(rgb)
        if smooth:
            prev = Handler.live_ema
            if prev is not None and prev.shape == rel_depth.shape:
                rel_depth = 0.7 * prev + 0.3 * rel_depth
            Handler.live_ema = rel_depth
        xyz, colors, flag = geometry.backproject(rgb, rel_depth, hfov_deg=HFOV_DEG,
                                                 stride=STRIDE, box=box)
        h, w = rgb.shape[:2]
        meta.update({
            "box": box,
            "depth_ms": round(depth_ms, 2),
            "frame_w": int(w),
            "frame_h": int(h),
            "hfov_deg": HFOV_DEG,
            "hfov_is_assumption": True,
            "device": self.model.device,
        })
        meta["total_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
        payload = geometry.encode(xyz, colors, flag, meta, hfov_deg=HFOV_DEG)
        sys.stderr.write(
            f"scene {self.path} points={len(flag)} flagged={int(flag.sum())} "
            f"depth_ms={meta['depth_ms']} total_ms={meta['total_ms']}\n")
        return payload

    def _scene_event(self, event_id: str, query: dict, t0: float):
        if not ID_RE.match(event_id):
            raise HttpError(400, "bad id")
        if "box" in query:
            box = parse_box(query["box"][0])
            if box is None:
                raise HttpError(400, "bad box")
        else:
            box = None
        event = fetch_event(event_id)
        if box is None:
            xywh = parse_box(event.get("box"))  # stored as [x, y, width, height] in pixels
            box = [xywh[0], xywh[1], xywh[0] + xywh[2], xywh[1] + xywh[3]] if xywh else None
        rgb = load_rgb(safe_frame_path(event.get("frame_path")))
        self._binary(self._render(rgb, box, {"event_id": int(event_id)}, t0))

    def _scene_live(self, t0: float):
        if self.live is None:
            raise HttpError(404, "SSW_DEMO_CLIP is not set")
        rgb, t_sec = self.live.read()
        self._binary(self._render(rgb, None, {"t_sec": t_sec, "smoothed": True}, t0, smooth=True))


def main():
    host = os.environ.get("SCENE_HOST", "127.0.0.1")
    port = int(os.environ.get("SCENE_PORT", "8300"))
    t0 = time.perf_counter()
    Handler.model = DepthModel(MODEL_DIR)
    sys.stderr.write(f"loaded {MODEL_NAME} on {Handler.model.device} in "
                     f"{(time.perf_counter() - t0):.1f} s\n")
    if DEMO_CLIP:
        Handler.live = LiveClip(DEMO_CLIP)
    server = ThreadingHTTPServer((host, port), Handler)
    sys.stderr.write(f"scene3d listening on {host}:{port}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
