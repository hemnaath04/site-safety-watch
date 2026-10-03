"""Smoke test for the box: does the local vLLM accept an image and answer?

Draws a simple scene (boxes in front of an EXIT door), sends it to the local model and prints
the latency, token usage and answer. Run on the GB10. Needs Pillow.

    python3 agent/box/vision_smoke.py
"""
import base64
import io
import json
import os
import time
import urllib.request

from PIL import Image, ImageDraw

BASE_URL = os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "nvidia/Qwen3.6-35B-A3B-NVFP4")


def draw_scene():
    img = Image.new("RGB", (960, 640), (205, 205, 200))
    d = ImageDraw.Draw(img)
    d.polygon([(0, 640), (960, 640), (700, 380), (260, 380)], fill=(150, 150, 145))  # floor
    d.rectangle([400, 150, 560, 400], fill=(120, 60, 40))  # door
    d.rectangle([440, 110, 520, 145], fill=(20, 140, 40))  # exit sign
    d.text((458, 120), "EXIT", fill=(255, 255, 255))
    d.rectangle([380, 300, 600, 470], fill=(170, 120, 60))  # boxes in front of the door
    d.text((440, 380), "BOXES", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def main():
    question = (
        "You are a workplace safety inspector. Describe the hazard in this image in one "
        'sentence, then answer with JSON {"hazard": string, "severity": "low|medium|high"}.'
    )
    body = {
        "model": MODEL,
        "max_tokens": 200,
        "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + draw_scene()}},
            {"type": "text", "text": question},
        ]}],
    }
    req = urllib.request.Request(
        BASE_URL + "/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    start = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        result = json.load(resp)
    seconds = time.time() - start
    print(json.dumps({
        "seconds": round(seconds, 2),
        "usage": result.get("usage"),
        "answer": result["choices"][0]["message"]["content"],
    }, indent=1))


if __name__ == "__main__":
    main()
