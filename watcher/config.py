"""Watcher settings. All runtime inference goes to the box's local vLLM.

The endpoint is read from VLLM_BASE_URL so we never hardcode another host. On a laptop
you run with the fake vision client, so the URL is not even used there.
"""
from __future__ import annotations

import os
from pathlib import Path

# Repo root is the parent of the watcher folder.
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
FRAMES_DIR = DATA_DIR / "frames"
DB_PATH = Path(os.environ.get("SSW_DB", DATA_DIR / "ssw.db"))

# Local vLLM on the box, OpenAI compatible. Never a cloud host.
VLLM_BASE_URL = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000/v1")
MODEL = os.environ.get("SSW_MODEL", "nvidia/Qwen3.6-35B-A3B-NVFP4")

# Sampling and detection.
SAMPLE_INTERVAL_SEC = float(os.environ.get("SSW_INTERVAL", "2"))
FRAME_WIDTH = int(os.environ.get("SSW_FRAME_WIDTH", "960"))
MIN_CONFIDENCE = float(os.environ.get("SSW_MIN_CONFIDENCE", "0.6"))

# De-duplication: same hazard and zone inside this window is one event.
DEDUP_WINDOW_MIN = float(os.environ.get("SSW_DEDUP_MIN", "5"))

# Vision call timeout and retry (malformed JSON retries once, then we skip).
VISION_TIMEOUT_SEC = float(os.environ.get("SSW_VISION_TIMEOUT", "30"))

# Motion gate: mean absolute pixel difference (0 to 255) over a small grayscale frame
# at or above which the scene counts as changed. Below it we skip the vision call.
MOTION_THRESHOLD = float(os.environ.get("SSW_MOTION_THRESHOLD", "3.0"))

# Face blur on the saved evidence frame. On by default, because the posted frame must not
# show a face (a hard team rule). It is a no-op when no face is detected.
BLUR_FACES = os.environ.get("SSW_BLUR", "1") not in ("0", "false", "False", "")


def ensure_dirs() -> None:
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
