"""Second verifier: a smaller local model (NVIDIA Cosmos) that confirms a candidate.

Used as a second opinion to cut false alarms. OpenAI compatible, on a local host only
(for example http://127.0.0.1:8001/v1). Off unless SSW_VERIFIER_URL is set. On any error
it returns True (fail open), so a flaky verifier never silently drops real hazards; the
drop-dead at 16:00 means we turn it off rather than depend on it.
"""
from __future__ import annotations

import base64
import json
import urllib.request

from . import config

VERIFY_PROMPT = (
    "You are confirming a workplace safety alert. Is an exit route or exit door really "
    "blocked in this frame? Answer with ONLY this JSON: "
    '{"blocked": true or false}'
)


class CosmosVerifier:
    def __init__(self, base_url=None, model=None, timeout=None):
        self.base_url = (base_url or config.VERIFIER_URL).rstrip("/")
        self.model = model or config.VERIFIER_MODEL
        self.timeout = timeout or config.VISION_TIMEOUT_SEC

    def confirms(self, jpeg_bytes: bytes, zone: str) -> bool:
        if not self.base_url:
            return True
        try:
            b64 = base64.b64encode(jpeg_bytes or b"").decode("ascii")
            payload = {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": VERIFY_PROMPT},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }],
                "temperature": 0,
                "max_tokens": 50,
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
            start, end = content.find("{"), content.rfind("}")
            obj = json.loads(content[start:end + 1])
            return bool(obj.get("blocked", True))
        except Exception:
            return True  # fail open; do not drop a real hazard on a verifier hiccup
