"""Vision client. Real client calls the box's local vLLM; fake client returns canned JSON.

Both expose the same classify(jpeg_bytes, zone) -> Event JSON interface, so the watcher,
the eval and the tests do not care which one is in use. On a laptop we always use the fake
client. Real calls happen only on the box, through Hemnaath.
"""
from __future__ import annotations

import base64
import json
import urllib.request

from . import config, rules


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of the model's reply, tolerant of stray text."""
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


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
        event = _extract_json(content)
        event["zone"] = zone  # zone comes from the clip config, never the model
        return event


class FakeVision:
    """Canned Event JSON for laptop testing. Same interface as RealVision.

    By default reports a blocked exit on every call. Pass a script (a list of hazards) to
    drive a sequence, for example ["none", "none", "blocked_exit"]. jpeg_bytes may be None.
    """

    def __init__(self, script=None, confidence=0.92):
        self.script = list(script) if script else None
        self.confidence = confidence
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
                "explanation": explanation}


def get_vision(fake: bool):
    return FakeVision() if fake else RealVision()
