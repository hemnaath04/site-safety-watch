"""Live multi-camera twin: people, exit door and blockage on a shared floor plan.

Runs on the GB10 inside the vLLM image (torch, transformers, opencv, numpy, Pillow present).
Threads: one reader per camera (latest frame only, files paced at real time), one detector
(RT-DETR v2 on the GPU, all cameras in one batch), one door checker (Qwen3.6 vision, one call
per camera in parallel, JSON schema output). Everything is served as JSON over stdlib HTTP.

Env:
  TWIN_CONFIG        config path, relative to SSW_REPO_ROOT if not absolute
                     (default agent/twin/cameras.json)
  SSW_REPO_ROOT      repo root for clip paths (default /repo)
  TWIN_HOST/PORT     bind address (default 127.0.0.1:8400)
  TWIN_DETECT_MS     detector period in ms (default 100)
  TWIN_DOOR_S        door check period in s (default 3)
  TWIN_DET_MODEL     RT-DETR v2 dir (default /models/rtdetr_v2_r18vd)
  TWIN_SCORE         person score threshold (default 0.5)
  TWIN_PERSON_LABEL  COCO person label id (default 0)
  VLLM_BASE_URL      local vLLM (default http://127.0.0.1:8000/v1)
  SSW_MODEL          vision model id (default nvidia/Qwen3.6-35B-A3B-NVFP4)
"""

import base64
import json
import math
import os
import re
import shutil
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import doors  # noqa: E402
import geometry  # noqa: E402
import syncclock  # noqa: E402
import tracker  # noqa: E402

POSE_PASSTHROUGH = ("z", "look_at", "hfov_deg")

REPO_ROOT = Path(os.environ.get("SSW_REPO_ROOT", "/repo")).resolve()
DETECT_MS = float(os.environ.get("TWIN_DETECT_MS", "100"))
DOOR_S = float(os.environ.get("TWIN_DOOR_S", "3"))
DET_MODEL_DIR = os.environ.get("TWIN_DET_MODEL", "/models/rtdetr_v2_r18vd")
SCORE_TH = float(os.environ.get("TWIN_SCORE", "0.5"))
PERSON_LABEL = int(os.environ.get("TWIN_PERSON_LABEL", "0"))
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
VISION_MODEL = os.environ.get("SSW_MODEL", "nvidia/Qwen3.6-35B-A3B-NVFP4")
STALE_S = 2.0
ROOM_MARGIN_M = 0.5
STATS_WINDOW_S = 10.0
CAM_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

DOOR_PROMPT = (
    "This is a CCTV frame of a room with an emergency exit door. Answer about that exit door "
    "only. door_visible: true if the exit door is in view. door_open: true if it is open. "
    "blocked: OSHA 29 CFR 1910.37 says exit routes must be free and unobstructed, so true if any "
    "movable item (standing table, stand, chair, cart, boxes, pallet, equipment) is placed in "
    "front of the door or in the floor area people use to reach it, even if someone could squeeze "
    "past. Permanent fixtures (built-in desks and seating rows, handrails, walls, pillars) and a "
    "person walking through are not a blockage. obstruction: the blocking object's box as "
    "[x1, y1, x2, y2] on a 0 to 1000 "
    "scale of the image, or null if not blocked."
)


def approach_zone(door: dict, walls, depth_m: float = 1.2, pad_m: float = 0.2):
    """Floor polygon in front of an exit door, on the room side: the egress approach that must
    stay clear. Used to show a blockage without trusting an uncalibrated camera homography."""
    (x1, y1), (x2, y2) = door["p1"], door["p2"]
    L = math.hypot(x2 - x1, y2 - y1) or 1.0
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    nx, ny = -uy, ux
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    if walls and not geometry.point_in_polygon((mx + 0.5 * nx, my + 0.5 * ny), walls):
        nx, ny = -nx, -ny
    a = (x1 - pad_m * ux, y1 - pad_m * uy)
    b = (x2 + pad_m * ux, y2 + pad_m * uy)
    return [[round(a[0], 3), round(a[1], 3)], [round(b[0], 3), round(b[1], 3)],
            [round(b[0] + depth_m * nx, 3), round(b[1] + depth_m * ny, 3)],
            [round(a[0] + depth_m * nx, 3), round(a[1] + depth_m * ny, 3)]]


def log(msg: str) -> None:
    sys.stderr.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def percentile(values, q):
    vals = sorted(values)
    if not vals:
        return None
    k = max(0, min(len(vals) - 1, math.ceil(q / 100.0 * len(vals)) - 1))
    return round(vals[k], 2)


def config_path() -> Path:
    p = Path(os.environ.get("TWIN_CONFIG", "agent/twin/cameras.json"))
    return p if p.is_absolute() else REPO_ROOT / p


def resolve_source(source: str):
    """URL strings pass through; files resolve under SSW_REPO_ROOT. Returns (src, is_file)."""
    if "://" in source:
        return source, False
    path = (REPO_ROOT / source).resolve()
    if not path.is_relative_to(REPO_ROOT):
        raise ValueError(f"camera source outside repo root: {source}")
    return str(path), True


class Camera:
    def __init__(self, cfg: dict):
        self.id = cfg["id"]
        if not CAM_ID_RE.match(self.id):
            raise ValueError(f"bad camera id: {self.id!r}")
        self.source, self.is_file = resolve_source(cfg["source"])
        self.loop = bool(cfg.get("loop", True))
        pose = cfg.get("pose") or {}
        self.pose = {"x": float(pose.get("x", 0)), "y": float(pose.get("y", 0)),
                     "yaw_deg": float(pose.get("yaw_deg", 0))}
        for key in POSE_PASSTHROUGH:
            if pose.get(key) is not None:
                self.pose[key] = pose[key]
        self.label = cfg.get("label")
        self.door_id = cfg.get("door_id")
        crop = cfg.get("door_crop")  # optional [x1, y1, x2, y2] source pixels around the exit door
        self.door_crop = [int(v) for v in crop] if isinstance(crop, (list, tuple)) and len(crop) == 4 else None
        self.sync_group = cfg.get("sync_group") or None
        self.start_offset_s = float(cfg.get("start_offset_s", 0.0))
        if not (math.isfinite(self.start_offset_s) and self.start_offset_s >= 0):
            raise ValueError(f"{self.id}: start_offset_s must be >= 0")
        self.group = None
        self.H = None
        self.set_floor_points(cfg.get("floor_points"))
        self.lock = threading.Lock()
        self.frame = None
        self.frame_t = 0.0
        self.times = deque(maxlen=240)
        self.boxes = []
        self.door_report = None

    def set_floor_points(self, fp):
        if fp and fp.get("pixels") and fp.get("meters"):
            self.H = geometry.homography(fp["pixels"], fp["meters"])

    def publish(self, frame):
        now = time.monotonic()
        with self.lock:
            self.frame = frame
            self.frame_t = now
            self.times.append(now)

    def latest(self):
        with self.lock:
            return self.frame, self.frame_t

    def fps(self):
        now = time.monotonic()
        with self.lock:
            ts = [t for t in self.times if now - t <= 2.0]
        if len(ts) < 2 or ts[-1] <= ts[0]:
            return 0.0
        return round((len(ts) - 1) / (ts[-1] - ts[0]), 2)

    def age_ms(self):
        with self.lock:
            if self.frame is None:
                return None
            return round((time.monotonic() - self.frame_t) * 1000.0, 1)

    def read_forever(self):
        if self.group is not None and self.is_file:
            return self.read_synced()
        while True:
            cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                log(f"{self.id}: cannot open source, retrying in 2 s")
                time.sleep(2.0)
                continue
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            if not 1.0 <= fps <= 120.0:
                fps = 25.0
            t0 = time.monotonic()
            n = 0
            while True:
                if self.is_file:
                    target = t0 + n / fps
                    now = time.monotonic()
                    if now < target:
                        time.sleep(target - now)
                    else:
                        behind = int((now - target) * fps)
                        for _ in range(min(behind, 30)):
                            if not cap.grab():
                                break
                            n += 1
                ok, frame = cap.read()
                if not ok:
                    break
                n += 1
                self.publish(frame)
            cap.release()
            if self.is_file and not self.loop:
                log(f"{self.id}: end of clip, not looping")
                return
            if not self.is_file:
                log(f"{self.id}: stream dropped, reconnecting")
                time.sleep(1.0)

    def read_synced(self):
        """Play this camera's file on its group's shared clock: seek on each new loop (and if
        more than half a second off), read frames in order in between."""
        group = self.group
        while True:
            cap = cv2.VideoCapture(self.source)
            if not cap.isOpened():
                log(f"{self.id}: cannot open source, retrying in 2 s")
                time.sleep(2.0)
                continue
            fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
            if not 1.0 <= fps <= 120.0:
                fps = 25.0
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if frames <= 0:
                log(f"{self.id}: no frame count, cannot sync; retrying in 5 s")
                cap.release()
                time.sleep(5.0)
                continue
            group.register(self.id, frames / fps)
            if not group.wait_ready() or self.id not in group.members:
                log(f"{self.id}: left out of sync group {group.name} "
                    f"(offset {self.start_offset_s} s past the end of the clip?)")
                cap.release()
                return
            log(f"{self.id}: synced in group {group.name}, offset {self.start_offset_s} s, "
                f"loop {group.loop_len:.2f} s, {fps:.2f} fps")
            next_idx = 0
            cycle = None
            while True:
                t, cyc = group.now()
                action, arg = syncclock.plan_step(
                    next_idx, syncclock.file_position(self.start_offset_s, t), fps, cyc != cycle)
                cycle = cyc
                if action == "seek":
                    cap.set(cv2.CAP_PROP_POS_FRAMES, arg)
                    next_idx = arg
                elif action == "sleep":
                    time.sleep(min(arg, 0.5))
                    continue
                elif action == "grab":
                    for _ in range(arg):
                        if not cap.grab():
                            break
                        next_idx += 1
                ok, frame = cap.read()
                if not ok:
                    # past the last decodable frame: wait for the loop to wrap, then seek
                    t_now, _ = group.now()
                    time.sleep(max(0.01, min(0.5, group.loop_len - t_now)))
                    cycle = None
                    continue
                next_idx += 1
                self.publish(frame)


class Detector:
    """RT-DETR v2 person detector, batched over cameras, fp16 on the GPU."""

    def __init__(self, model_dir: str):
        import torch
        # On the GB10 (sm_121) this torch build's cuDNN has no fp16 conv engine; native CUDA works.
        torch.backends.cudnn.enabled = False
        from transformers import AutoImageProcessor, RTDetrV2ForObjectDetection

        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.dtype = torch.float16 if self.device == "cuda" else torch.float32
        self.processor = AutoImageProcessor.from_pretrained(model_dir)
        self.model = RTDetrV2ForObjectDetection.from_pretrained(
            model_dir, dtype=self.dtype).to(self.device).eval()
        size = getattr(self.processor, "size", None) or {}
        self.in_h = int(size.get("height", 640))
        self.in_w = int(size.get("width", 640))

    def _sync(self):
        if self.device == "cuda":
            self.torch.cuda.synchronize()

    def detect(self, frames_rgb):
        """frames_rgb: list of HxWx3 uint8. Returns ([[(box, score), ...] per frame], batch_ms)."""
        torch = self.torch
        sizes = [f.shape[:2] for f in frames_rgb]
        small = [cv2.resize(f, (self.in_w, self.in_h), interpolation=cv2.INTER_LINEAR)
                 for f in frames_rgb]
        inputs = self.processor(images=small, return_tensors="pt")
        pv = inputs["pixel_values"].to(self.device, dtype=self.dtype)
        with torch.inference_mode():
            self._sync()
            t0 = time.perf_counter()
            out = self.model(pixel_values=pv)
            self._sync()
            batch_ms = (time.perf_counter() - t0) * 1000.0
            res = self.processor.post_process_object_detection(
                types.SimpleNamespace(logits=out.logits.float(), pred_boxes=out.pred_boxes.float()),
                threshold=SCORE_TH, target_sizes=[list(s) for s in sizes])
        per_frame = []
        for r in res:
            people = []
            for score, label, box in zip(r["scores"].tolist(), r["labels"].tolist(),
                                         r["boxes"].tolist()):
                if int(label) == PERSON_LABEL and score >= SCORE_TH:
                    people.append(([round(v, 1) for v in box], round(score, 3)))
            per_frame.append(people)
        return per_frame, batch_ms

    def gpu_memory_mb(self):
        if self.device != "cuda":
            return None, None
        t = self.torch.cuda
        return round(t.memory_allocated() / 2**20, 1), round(t.memory_reserved() / 2**20, 1)


class Twin:
    def __init__(self, cfg_path: Path, detector: Detector):
        self.cfg_path = cfg_path
        self.cfg_lock = threading.Lock()
        cfg = json.loads(cfg_path.read_text())
        self.room = cfg["room"]
        self.walls = [tuple(map(float, p)) for p in self.room.get("walls", [])]
        self.cameras = {c["id"]: Camera(c) for c in cfg["cameras"]}
        self.groups = {}
        for name in sorted({c.sync_group for c in self.cameras.values() if c.sync_group}):
            members = [c for c in self.cameras.values() if c.sync_group == name and c.is_file]
            if not members:
                continue
            group = syncclock.SyncGroup(name, {c.id: c.start_offset_s for c in members})
            for c in members:
                c.group = group
            self.groups[name] = group
        self.detector = detector
        self.tracker = tracker.Tracker(max_speed=6.0, slack_m=1.5)  # loose gate: mappings are rough
        self.state_lock = threading.Lock()
        self.people = []
        self.doors = {d["id"]: {"open": None, "blocked": None, "obstruction_floor": None,
                                "updated": None} for d in self.room.get("doors", [])}
        self.door_zones = {d["id"]: approach_zone(d, self.walls) for d in self.room.get("doors", [])
                           if d.get("p1") and d.get("p2")}
        self.primary = {}
        self.batch_ms = deque(maxlen=600)
        self.detected = deque(maxlen=2000)
        self.door_ms = deque(maxlen=200)
        door_cams = [c for c in self.cameras.values() if c.door_id]
        self.pool = ThreadPoolExecutor(max_workers=max(1, len(door_cams)))

    # threads

    def start(self):
        for cam in self.cameras.values():
            threading.Thread(target=cam.read_forever, name=f"read-{cam.id}", daemon=True).start()
        threading.Thread(target=self._loop, args=(DETECT_MS / 1000.0, self.detect_once),
                         name="detect", daemon=True).start()
        threading.Thread(target=self._loop, args=(DOOR_S, self.doors_once),
                         name="doors", daemon=True).start()

    def _loop(self, period, fn):
        while True:
            t0 = time.monotonic()
            try:
                fn()
            except Exception as exc:
                log(f"{threading.current_thread().name} error: {exc!r}")
            time.sleep(max(0.0, period - (time.monotonic() - t0)))

    def _fresh(self, cam):
        frame, t = cam.latest()
        if frame is None or time.monotonic() - t > STALE_S:
            return None
        return frame

    def _in_room(self, x, y):
        if not self.walls:
            return True
        if geometry.point_in_polygon((x, y), self.walls):
            return True
        xs = [p[0] for p in self.walls]
        ys = [p[1] for p in self.walls]
        return (min(xs) - ROOM_MARGIN_M <= x <= max(xs) + ROOM_MARGIN_M
                and min(ys) - ROOM_MARGIN_M <= y <= max(ys) + ROOM_MARGIN_M)

    def detect_once(self):
        cams, frames = [], []
        for cam in self.cameras.values():
            f = self._fresh(cam)
            if f is not None:
                cams.append(cam)
                frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        if not frames:
            return
        results, ms = self.detector.detect(frames)
        now = time.monotonic()
        per_cam = {}
        for cam, people in zip(cams, results):
            cam.boxes = people
            found = []
            if cam.H is not None and people:
                feet = geometry.project(cam.H, [geometry.feet_point(b) for b, _ in people])
                for x, y in feet:
                    if math.isfinite(x) and math.isfinite(y) and self._in_room(x, y):
                        found.append((float(x), float(y), cam.id))
            per_cam[cam.id] = (cam, found)
        # Angles of one synced take see the same people, and the floor mappings are not
        # calibrated well enough to fuse them, so each group counts people from one camera:
        # the one that sees the most, sticky on ties so pins do not jump between cameras.
        chosen = {}
        for cid, (cam, found) in per_cam.items():
            key = cam.sync_group or cid
            cur = chosen.get(key)
            if (cur is None or len(found) > len(cur[1])
                    or (len(found) == len(cur[1]) and self.primary.get(key) == cid)):
                chosen[key] = (cid, found)
        dets = []
        for key, (cid, found) in chosen.items():
            self.primary[key] = cid
            dets.extend(found)
        tracks = self.tracker.update(tracker.fuse(dets), now)
        # Pins only for people seen in this frame, so a jittery projection never leaves a ghost.
        tracks = [tr.as_dict() for tr in self.tracker.tracks if tr.last_seen == now]
        with self.state_lock:
            self.people = tracks
            self.batch_ms.append(ms)
            self.detected.append((now, len(frames)))

    def _ask_door(self, cam):
        frame = self._fresh(cam)
        if frame is None:
            return None
        ox = oy = 0
        if cam.door_crop:
            fh, fw = frame.shape[:2]
            x1, y1, x2, y2 = cam.door_crop
            x1, x2 = max(0, min(x1, fw - 1)), max(1, min(x2, fw))
            y1, y2 = max(0, min(y1, fh - 1)), max(1, min(y2, fh))
            if x2 > x1 and y2 > y1:
                frame, ox, oy = frame[y1:y2, x1:x2], x1, y1
        h, w = frame.shape[:2]
        send = frame if w <= 960 else cv2.resize(frame, (960, round(h * 960 / w)))
        ok, jpg = cv2.imencode(".jpg", send, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None
        body = {
            "model": VISION_MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": DOOR_PROMPT},
                {"type": "image_url", "image_url": {
                    "url": "data:image/jpeg;base64," + base64.b64encode(jpg.tobytes()).decode()}},
            ]}],
            "temperature": 0,
            "max_tokens": 120,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "door_state", "schema": doors.DOOR_SCHEMA, "strict": True}},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        req = urllib.request.Request(f"{VLLM_BASE_URL}/chat/completions",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            log(f"door {cam.id}: vision call failed: {exc!r}")
            return None
        ms = (time.perf_counter() - t0) * 1000.0
        usage = data.get("usage") or {}
        log(f"door {cam.id}: model={data.get('model', VISION_MODEL)} ms={ms:.0f} "
            f"prompt_tokens={usage.get('prompt_tokens')} "
            f"completion_tokens={usage.get('completion_tokens')}")
        with self.state_lock:
            self.door_ms.append(ms)
        try:
            report = doors.validate_report(
                json.loads(data["choices"][0]["message"]["content"]))
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            report = None
        if report is None:
            log(f"door {cam.id}: answer did not fit the schema")
            return None
        report["cam"] = cam.id
        report["door_id"] = cam.door_id
        report["obstruction_px"] = None
        report["obstruction_floor"] = None
        if report["blocked"] and report["obstruction"]:
            px = geometry.scale_box_1000(report["obstruction"], w, h)
            px = [px[0] + ox, px[1] + oy, px[2] + ox, px[3] + oy]  # back to full-frame pixels
            report["obstruction_px"] = px
        if report["blocked"]:
            report["obstruction_floor"] = self.door_zones.get(cam.door_id)
        cam.door_report = report
        return report

    def doors_once(self):
        cams = [c for c in self.cameras.values() if c.door_id]
        if not cams:
            return
        reports = [r for r in self.pool.map(self._ask_door, cams) if r]
        stamp = round(time.time(), 3)
        for door_id in {c.door_id for c in cams}:
            merged = doors.merge_door([r for r in reports if r["door_id"] == door_id])
            if merged is None:
                continue
            with self.state_lock:
                self.doors[door_id] = {**merged, "updated": stamp}

    # views

    def config_view(self):
        return {
            "room": self.room,
            "cameras": [{"id": c.id, "label": c.label, "pose": c.pose, "door_id": c.door_id,
                         "sync_group": c.sync_group, "calibrated": c.H is not None}
                        for c in self.cameras.values()],
        }

    def state_view(self):
        with self.state_lock:
            people = list(self.people)
            door_state = {k: dict(v) for k, v in self.doors.items()}
        return {
            "t": round(time.time(), 3),
            "people": people,
            "doors": [{"id": k, "open": v.get("open"), "blocked": v.get("blocked"),
                       "obstruction_floor": v.get("obstruction_floor"),
                       "updated": v.get("updated")} for k, v in door_state.items()],
            "cameras": [{"id": c.id, "fps": c.fps(), "people_in_view": len(c.boxes),
                         "last_frame_age_ms": c.age_ms()} for c in self.cameras.values()],
            "sync": {name: g.view() for name, g in self.groups.items()},
        }

    def stats_view(self):
        now = time.monotonic()
        with self.state_lock:
            batch = list(self.batch_ms)
            recent = [(t, n) for t, n in self.detected if now - t <= STATS_WINDOW_S]
            door_ms = list(self.door_ms)
        detected_fps = None
        if len(recent) >= 2 and recent[-1][0] > recent[0][0]:
            detected_fps = round(sum(n for _, n in recent[1:]) / (recent[-1][0] - recent[0][0]), 2)
        alloc, reserved = self.detector.gpu_memory_mb()
        return {
            "device": self.detector.device,
            "detector": {
                "batch_ms_p50": percentile(batch, 50),
                "batch_ms_p95": percentile(batch, 95),
                "batches": len(batch),
                "batch_size_mean": round(sum(n for _, n in recent) / len(recent), 2)
                if recent else None,
            },
            "cameras": [{"id": c.id, "fps": c.fps()} for c in self.cameras.values()],
            "detected_frames_per_s": detected_fps,
            "door_check_ms_p50": percentile(door_ms, 50),
            "door_checks": len(door_ms),
            "gpu_mem_allocated_mb": alloc,
            "gpu_mem_reserved_mb": reserved,
            "window_s": STATS_WINDOW_S,
            "detect_period_ms": DETECT_MS,
            "door_period_s": DOOR_S,
        }

    def camera_jpeg(self, cam, raw=False):
        frame, _ = cam.latest()
        if frame is None:
            return None
        if raw:
            ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            return jpg.tobytes() if ok else None
        h, w = frame.shape[:2]
        s = 640.0 / w
        img = cv2.resize(frame, (640, max(1, round(h * s))))
        for box, score in list(cam.boxes):
            x1, y1, x2, y2 = (int(round(v * s)) for v in box)
            cv2.rectangle(img, (x1, y1), (x2, y2), (80, 220, 80), 2)
            cv2.putText(img, f"{score:.2f}", (x1, max(12, y1 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (80, 220, 80), 1, cv2.LINE_AA)
        rep = cam.door_report
        label = f"{cam.id}"
        if cam.door_id:
            with self.state_lock:
                d = dict(self.doors.get(cam.door_id) or {})
            if d.get("blocked"):
                word = "BLOCKED"
            elif d.get("open") is None:
                word = "UNKNOWN"
            else:
                word = "OPEN" if d.get("open") else "CLOSED"
            label += f"  {cam.door_id}: {word}"
            if rep and rep.get("obstruction_px"):
                x1, y1, x2, y2 = (int(round(v * s)) for v in rep["obstruction_px"])
                cv2.rectangle(img, (x1, y1), (x2, y2), (40, 40, 230), 2)
        cv2.rectangle(img, (0, 0), (640, 22), (0, 0, 0), -1)
        cv2.putText(img, label, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1,
                    cv2.LINE_AA)
        ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return jpg.tobytes() if ok else None

    def calibration_view(self, cam):
        with self.cfg_lock:
            cfg = json.loads(self.cfg_path.read_text())
        entry = next((c for c in cfg["cameras"] if c["id"] == cam.id), {})
        frame, _ = cam.latest()
        h, w = frame.shape[:2] if frame is not None else (None, None)
        return {"cam": cam.id, "floor_points": entry.get("floor_points"),
                "frame_w": w, "frame_h": h, "room": self.room}

    def save_calibration(self, cam, body):
        pixels = body.get("pixels") if isinstance(body, dict) else None
        meters = body.get("meters") if isinstance(body, dict) else None
        for pts in (pixels, meters):
            if (not isinstance(pts, list) or len(pts) != 4
                    or not all(isinstance(p, list) and len(p) == 2
                               and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                                       and math.isfinite(v) for v in p) for p in pts)):
                raise ValueError("need 4 pixel points and 4 meter points, each [a, b]")
        geometry.homography(pixels, meters)
        fp = {"pixels": [[round(float(u), 1), round(float(v), 1)] for u, v in pixels],
              "meters": [[round(float(x), 3), round(float(y), 3)] for x, y in meters]}
        with self.cfg_lock:
            cfg = json.loads(self.cfg_path.read_text())
            entry = next((c for c in cfg["cameras"] if c["id"] == cam.id), None)
            if entry is None:
                raise KeyError(cam.id)
            entry["floor_points"] = fp
            shutil.copyfile(self.cfg_path, self.cfg_path.with_name(self.cfg_path.name + ".bak"))
            tmp = self.cfg_path.with_name(self.cfg_path.name + ".tmp")
            tmp.write_text(json.dumps(cfg, indent=2) + "\n")
            tmp.replace(self.cfg_path)
        cam.set_floor_points(fp)
        return fp


class Handler(BaseHTTPRequestHandler):
    server_version = "twin/1"
    twin: Twin = None

    def log_message(self, fmt, *args):
        if "/twin/state" in self.path or "/twin/camera/" in self.path:
            return  # polled many times a second; keep the log readable
        log(fmt % args)

    def _send(self, status, payload: bytes, ctype: str):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status, body):
        self._send(status, json.dumps(body).encode(), "application/json")

    def _cam(self, cam_id):
        if not CAM_ID_RE.match(cam_id):
            self._json(400, {"error": "bad camera id"})
            return None
        cam = self.twin.cameras.get(cam_id)
        if cam is None:
            self._json(404, {"error": "unknown camera"})
        return cam

    def do_GET(self):
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        query = parse_qs(url.query)
        try:
            if parts[:1] != ["twin"]:
                return self._json(404, {"error": "no such route"})
            rest = parts[1:]
            if rest == ["health"]:
                return self._json(200, {"ok": True, "device": self.twin.detector.device,
                                        "cameras": len(self.twin.cameras)})
            if rest == ["config"]:
                return self._json(200, self.twin.config_view())
            if rest == ["state"]:
                return self._json(200, self.twin.state_view())
            if rest == ["stats"]:
                return self._json(200, self.twin.stats_view())
            if len(rest) == 2 and rest[0] == "camera" and rest[1].endswith(".jpg"):
                cam = self._cam(rest[1][:-4])
                if cam is None:
                    return
                jpg = self.twin.camera_jpeg(cam, raw=query.get("raw", ["0"])[0] == "1")
                if jpg is None:
                    return self._json(503, {"error": "no frame yet"})
                return self._send(200, jpg, "image/jpeg")
            if len(rest) == 2 and rest[0] == "calibrate":
                cam = self._cam(rest[1])
                if cam is None:
                    return
                if query.get("format", [""])[0] == "json":
                    return self._json(200, self.twin.calibration_view(cam))
                return self._send(200, (HERE / "calibrate.html").read_bytes(),
                                  "text/html; charset=utf-8")
            return self._json(404, {"error": "no such route"})
        except Exception as exc:  # last resort: never leak a traceback to the client
            log(f"internal error: {exc!r}")
            self._json(500, {"error": "internal error"})

    def do_POST(self):
        parts = [p for p in urlparse(self.path).path.split("/") if p]
        try:
            if len(parts) != 3 or parts[:2] != ["twin", "calibrate"]:
                return self._json(404, {"error": "no such route"})
            cam = self._cam(parts[2])
            if cam is None:
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if not 0 < length <= 65536:
                return self._json(400, {"error": "bad body"})
            try:
                body = json.loads(self.rfile.read(length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return self._json(400, {"error": "bad json"})
            try:
                fp = self.twin.save_calibration(cam, body)
            except ValueError as exc:
                return self._json(400, {"error": str(exc)})
            except KeyError:
                return self._json(404, {"error": "camera not in config file"})
            log(f"calibration saved for {cam.id}")
            return self._json(200, {"ok": True, "floor_points": fp})
        except Exception as exc:
            log(f"internal error: {exc!r}")
            self._json(500, {"error": "internal error"})


def main():
    host = os.environ.get("TWIN_HOST", "127.0.0.1")
    port = int(os.environ.get("TWIN_PORT", "8400"))
    cfg_path = config_path()
    t0 = time.perf_counter()
    detector = Detector(DET_MODEL_DIR)
    log(f"loaded RT-DETR v2 on {detector.device} in {time.perf_counter() - t0:.1f} s")
    twin = Twin(cfg_path, detector)
    log(f"config {cfg_path}: {len(twin.cameras)} cameras, doors {list(twin.doors)}")
    Handler.twin = twin
    twin.start()
    server = ThreadingHTTPServer((host, port), Handler)
    log(f"twin listening on {host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
