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

# --- Accuracy switches (post-lock), each off by default and measured on and off ---
# Temporal voting, for example "3/4" (hazard must be seen in 3 of the last 4 samples).
VOTE_SPEC = os.environ.get("SSW_VOTE", "")
# Enhance the frame sent to the model: exit-zone crop, 2x upscale, CLAHE.
ENHANCE = os.environ.get("SSW_ENHANCE", "0") not in ("0", "false", "False", "")
ENHANCE_SCALE = float(os.environ.get("SSW_ENHANCE_SCALE", "2.0"))
# Ask the model for the obstruction box and require it to overlap the exit zone.
LOCATE = os.environ.get("SSW_LOCATE", "0") not in ("0", "false", "False", "")
# Minimum fraction of the obstruction box that must fall inside the exit zone.
LOCATE_MIN_OVERLAP = float(os.environ.get("SSW_LOCATE_MIN_OVERLAP", "0.1"))
# Second verifier model (NVIDIA Cosmos) OpenAI-compatible URL, for example
# http://127.0.0.1:8001/v1. Empty = off. Must be a local host.
VERIFIER_URL = os.environ.get("SSW_VERIFIER_URL", "")
VERIFIER_MODEL = os.environ.get("SSW_VERIFIER_MODEL", "nvidia/Cosmos-Reason2-2B")
# Zone config with exit boxes, for example {"exit_a": {"exit_box": [x, y, w, h]}}.
ZONES_FILE = Path(os.environ.get("SSW_ZONES", REPO_ROOT / "watcher" / "zones.json"))
# Per-frame decision log for debugging and the eval.
DECISIONS_LOG = Path(os.environ.get("SSW_DECISIONS", DATA_DIR / "decisions.jsonl"))

# Auto-resolution: after this many clear checks in a row in a zone, open events there are
# marked resolved with the time and a frame. On by default (it only closes events, it never
# blocks detection); disable with --no-auto-resolve or SSW_AUTO_RESOLVE=0.
AUTO_RESOLVE = os.environ.get("SSW_AUTO_RESOLVE", "1") not in ("0", "false", "False", "")
CLEARS_TO_RESOLVE = int(os.environ.get("SSW_CLEARS_TO_RESOLVE", "2"))

# Draw the box and label on the saved hazard frame (after blur). On by default; a frame with
# no box is left plain.
ANNOTATE = os.environ.get("SSW_ANNOTATE", "1") not in ("0", "false", "False", "")

# Local timezone for stored timestamps. Inside the vLLM container there is no system TZ, so
# astimezone() falls back to UTC; use an explicit zone instead. SSW_TZ wins, then TZ, then
# a sensible venue default.
TZ_NAME = os.environ.get("SSW_TZ") or os.environ.get("TZ") or "America/New_York"


def now_local():
    """Timezone-aware 'now' in TZ_NAME, with a safe fallback to the machine's local zone."""
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(TZ_NAME))
    except Exception:
        return datetime.now().astimezone()


def ensure_dirs() -> None:
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
