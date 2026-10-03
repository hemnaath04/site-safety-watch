"""Vision client. Real client calls the box's local vLLM; fake client returns canned JSON.

Both expose the same classify(jpeg_bytes, zone) -> Event JSON interface, so the watcher,
the eval and the tests do not care which one is in use. On a laptop we always use the fake
client. Real calls happen only on the box, through Hemnaath.
"""
from __future__ import annotations

import base64
import json
import urllib.request

from . import config, locate, rules


def _jpeg_dims(jpeg_bytes):
    """Return (width, height) of a JPEG, or (None, None) if it cannot be read."""
    try:
        import cv2
        import numpy as np
        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None, None
        h, w = img.shape[:2]
        return w, h
    except Exception:
        return None, None


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of the model's reply, tolerant of stray text."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


def to_event(raw: dict, zone: str) -> dict:
    """Map the raw model schema {exit_visible, blocked, box, confidence, explanation} to
    the internal event {hazard, zone, confidence, explanation, box}. A blocked exit needs
    an exit to be visible and blocked; otherwise the hazard is none.
    """
    exit_visible = bool(raw.get("exit_visible"))
    blocked = bool(raw.get("blocked"))
    hazard = "blocked_exit" if (exit_visible and blocked) else "none"
    try:
        conf = float(raw.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        conf = 0.0
    return {
        "hazard": hazard,
        "zone": zone,
        "confidence": conf,
        "explanation": raw.get("explanation", "") or "",
        "box": raw.get("box") if hazard == "blocked_exit" else None,
        # exit_visible is kept so auto-resolution can tell "exit visible and clear" apart from
        # "no exit in frame" (we only resolve when the exit is visible and not blocked).
        "exit_visible": exit_visible,
    }


class RealVision:
    """Calls http://127.0.0.1:8000/v1/chat/completions on the box (OpenAI compatible)."""

    def __init__(self, base_url=None, model=None, timeout=None):
        self.base_url = (base_url or config.VLLM_BASE_URL).rstrip("/")
        self.model = model or config.MODEL
        self.timeout = timeout or config.VISION_TIMEOUT_SEC

    def classify(self, jpeg_bytes: bytes, zone: str, prompt: str | None = None) -> dict:
        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or rules.VISION_PROMPT},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
            "temperature": 0,
            "max_tokens": 200,
            "chat_template_kwargs": {"enable_thinking": False},
            # Enforce the JSON schema so the reply is always well formed. response_format is
            # the OpenAI-compatible form; guided_json is the vLLM-native fallback.
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "sighting", "schema": rules.VISION_SCHEMA},
            },
            "guided_json": rules.VISION_SCHEMA,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        event = to_event(_extract_json(content), zone)
        # Qwen returns the box as 0..1000 xyxy of the image it saw (this jpeg); convert it to
        # pixel [x, y, w, h] of that image so the overlap check and the stored box are right.
        if event.get("box"):
            w, h = _jpeg_dims(jpeg_bytes)
            if w and h:
                event["box"] = locate.qwen_xyxy1000_to_xywh(event["box"], w, h)
        return event


class FakeVision:
    """Canned Event JSON for laptop testing. Same interface as RealVision.

    By default reports a blocked exit on every call. Pass a script (a list of hazards) to
    drive a sequence, for example ["none", "none", "blocked_exit"]. jpeg_bytes may be None.
    """

    def __init__(self, script=None, confidence=0.92, box=None):
        self.script = list(script) if script else None
        self.confidence = confidence
        self.box = box
        self._i = 0

    def classify(self, jpeg_bytes, zone: str, prompt: str | None = None) -> dict:
        if self.script is not None:
            hazard = self.script[min(self._i, len(self.script) - 1)]
            self._i += 1
        else:
            hazard = "blocked_exit"
        if hazard == "blocked_exit":
            explanation = "a cart is parked in front of the exit door"
            conf = self.confidence
        else:
            explanation = "the exit route is clear"
            conf = 0.95
        return {"hazard": hazard, "zone": zone, "confidence": conf,
                "explanation": explanation, "box": self.box, "exit_visible": True}


def get_vision(fake: bool):
    return FakeVision() if fake else RealVision()
