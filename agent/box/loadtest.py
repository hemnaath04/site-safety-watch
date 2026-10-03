"""How many CCTV cameras can one GB10 watch? Camera-load test against the local vLLM.

Each simulated camera sends one frame every --interval seconds (frames cycle through real
clips) with the exit check prompt (JSON schema, thinking off). The camera count ramps through
--levels; for each level we record request latency, achieved checks per camera, and GPU
utilization, power and memory sampled once a second with nvidia-smi.

Run on the box inside the vLLM image (it has OpenCV):
  docker run --rm --network host --gpus all -v ~/site-safety-watch:/repo -w /repo \
    --entrypoint python3 gb10/vllm-spark:local agent/box/loadtest.py --levels 1,2,4,8,16
"""
import argparse
import base64
import glob
import json
import os
import statistics
import subprocess
import threading
import time
import urllib.request

import cv2

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["exit_visible", "blocked", "confidence"],
    "properties": {
        "exit_visible": {"type": "boolean"},
        "blocked": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}
PROMPT = ("You are a workplace safety inspector watching a CCTV frame. Is an exit door visible, "
          "and is it blocked by an object left in front of it?")


def load_frames(pattern, per_clip, width):
    frames = []
    for path in sorted(glob.glob(pattern)):
        cap = cv2.VideoCapture(path)
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        for i in range(per_clip):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(i * n / per_clip))
            ok, fr = cap.read()
            if not ok:
                continue
            h, w = fr.shape[:2]
            fr = cv2.resize(fr, (width, int(h * width / w)))
            frames.append(base64.b64encode(cv2.imencode(".jpg", fr, [cv2.IMWRITE_JPEG_QUALITY, 85])[1]).decode())
    return frames


def ask(base_url, model, b64, timeout):
    body = {
        "model": model, "max_tokens": 60, "temperature": 0,
        "chat_template_kwargs": {"enable_thinking": False},
        "response_format": {"type": "json_schema", "json_schema": {"name": "v", "schema": SCHEMA, "strict": True}},
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            {"type": "text", "text": PROMPT}]}],
    }
    req = urllib.request.Request(base_url + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        json.load(r)
    return time.time() - t


def gpu_sampler(stop, samples):
    while not stop.is_set():
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu,power.draw",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
            util, power = [float(x) for x in out.strip().split(",")[:2]]
            samples.append((util, power))
        except Exception:
            pass
        stop.wait(1.0)


def run_level(k, frames, args):
    lat, errors = [], [0]
    stop = threading.Event()
    lock = threading.Lock()

    def camera(cam):
        i = cam * 7
        time.sleep(args.interval * cam / max(k, 1))  # spread start times like real cameras
        while not stop.is_set():
            t0 = time.time()
            try:
                dt = ask(args.base_url, args.model, frames[i % len(frames)], args.timeout)
                with lock:
                    lat.append(dt)
            except Exception:
                with lock:
                    errors[0] += 1
            i += 1
            stop.wait(max(0.0, args.interval - (time.time() - t0)))

    samples = []
    threads = [threading.Thread(target=camera, args=(c,), daemon=True) for c in range(k)]
    sampler = threading.Thread(target=gpu_sampler, args=(stop, samples), daemon=True)
    sampler.start()
    for t in threads:
        t.start()
    time.sleep(args.duration)
    stop.set()
    for t in threads:
        t.join(timeout=args.timeout + 2)
    lat.sort()
    q = lambda p: round(lat[min(len(lat) - 1, int(p * len(lat)))], 2) if lat else None
    utils = [u for u, _ in samples]
    powers = [p for _, p in samples]
    return {
        "cameras": k,
        "interval_s": args.interval,
        "duration_s": args.duration,
        "checks": len(lat),
        "errors": errors[0],
        "checks_per_camera_per_min": round(len(lat) / k / (args.duration / 60), 1),
        "target_checks_per_camera_per_min": round(60 / args.interval, 1),
        "latency_p50_s": q(0.5),
        "latency_p95_s": q(0.95),
        "latency_max_s": round(lat[-1], 2) if lat else None,
        "gpu_util_mean_pct": round(statistics.mean(utils), 1) if utils else None,
        "gpu_util_max_pct": max(utils) if utils else None,
        "power_mean_w": round(statistics.mean(powers), 1) if powers else None,
        "power_max_w": max(powers) if powers else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=os.environ.get("VLLM_BASE_URL", "http://127.0.0.1:8000/v1"))
    ap.add_argument("--model", default=os.environ.get("SSW_MODEL", "nvidia/Qwen3.6-35B-A3B-NVFP4"))
    ap.add_argument("--clips", default="data/clips/9[0-3]_web_*[A-Z].mp4")
    ap.add_argument("--levels", default="1,2,4,8,16")
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--duration", type=float, default=40.0)
    ap.add_argument("--timeout", type=float, default=60.0)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--out", default="data/loadtest.json")
    args = ap.parse_args()
    frames = load_frames(args.clips, 12, args.width)
    print(f"{len(frames)} frames from {args.clips}", flush=True)
    ask(args.base_url, args.model, frames[0], args.timeout)  # warm up
    results = []
    for k in [int(x) for x in args.levels.split(",")]:
        r = run_level(k, frames, args)
        results.append(r)
        print(json.dumps(r), flush=True)
        with open(args.out, "w") as f:
            json.dump({"model": args.model, "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                       "results": results}, f, indent=1)


if __name__ == "__main__":
    main()
