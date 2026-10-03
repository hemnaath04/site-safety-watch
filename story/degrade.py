"""Make a bad-footage copy of every clip, to prove the system works on cheap cameras.

Leader's recipe (ffmpeg): scale to 640x360, drop brightness and contrast, add noise, low bitrate.
  ffmpeg -i IN.mp4 -vf "scale=640:360,eq=brightness=-0.12:contrast=0.85,noise=alls=12:allf=t" \
         -c:v libx264 -b:v 300k -an OUT_cctv360.mp4

This script runs that command for each clip in labels.csv when ffmpeg is present (the box).
If ffmpeg is missing (a laptop), it falls back to OpenCV for both videos and photos so you can
still test the harness. The fallback is an approximation; the box run uses the exact ffmpeg filter.

It also prints the labels rows to add (quality=degraded360); pass --append to write them into
labels.csv for you.

Usage:
  python -m story.degrade --clips-dir data/clips --labels story/labels.csv
  python -m story.degrade --clips-dir data/clips --labels story/labels.csv --append
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VF = "scale=640:360,eq=brightness=-0.12:contrast=0.85,noise=alls=12:allf=t"


def _has_ffmpeg():
    return shutil.which("ffmpeg") is not None


def _degrade_video_ffmpeg(src: Path, dst: Path) -> bool:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
           "-vf", VF, "-c:v", "libx264", "-b:v", "300k", "-an", str(dst)]
    return subprocess.run(cmd).returncode == 0


def _degrade_with_cv2(src: Path, dst: Path) -> bool:
    import cv2
    import numpy as np

    def deg_frame(frame):
        frame = cv2.resize(frame, (640, 360), interpolation=cv2.INTER_AREA)
        frame = cv2.convertScaleAbs(frame, alpha=0.85, beta=-31)  # contrast 0.85, brightness ~ -0.12
        noise = np.random.normal(0, 12, frame.shape).astype(np.int16)
        return np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    if src.suffix.lower() in (".jpg", ".jpeg", ".png"):
        img = cv2.imread(str(src))
        if img is None:
            return False
        return bool(cv2.imwrite(str(dst), deg_frame(img)))

    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        return False
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    writer = cv2.VideoWriter(str(dst), cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 360))
    ok_any = False
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        writer.write(deg_frame(fr))
        ok_any = True
    cap.release()
    writer.release()
    return ok_any


def degraded_name(clip: str) -> str:
    p = Path(clip)
    suffix = p.suffix if p.suffix.lower() in (".jpg", ".jpeg", ".png") else ".mp4"
    return f"{p.stem}_cctv360{suffix}"


def main(argv=None):
    p = argparse.ArgumentParser(description="Make degraded (cctv360) copies of every clip")
    p.add_argument("--clips-dir", default=str(REPO_ROOT / "data" / "clips"))
    p.add_argument("--labels", default=str(REPO_ROOT / "story" / "labels.csv"))
    p.add_argument("--append", action="store_true", help="append degraded360 rows to labels.csv")
    args = p.parse_args(argv)

    clips_dir = Path(args.clips_dir)
    use_ffmpeg = _has_ffmpeg()
    print(f"using {'ffmpeg (exact recipe)' if use_ffmpeg else 'OpenCV fallback (approximate)'}")

    with open(args.labels, newline="", encoding="utf-8") as fh:
        rows = [dict(r) for r in csv.DictReader(fh)]

    new_rows = []
    for r in rows:
        clip = (r.get("clip") or "").strip()
        if not clip or clip.endswith(("_cctv360.mp4", "_cctv360.jpg", "_cctv360.jpeg")):
            continue
        src = clips_dir / clip
        if not src.exists():
            print(f"skip (missing): {clip}")
            continue
        out_name = degraded_name(clip)
        dst = clips_dir / out_name
        is_video = src.suffix.lower() == ".mp4"
        ok = (_degrade_video_ffmpeg(src, dst) if (use_ffmpeg and is_video)
              else _degrade_with_cv2(src, dst))
        print(("ok  " if ok else "FAIL") + f" {out_name}")
        if ok:
            new_rows.append({"clip": out_name, "hazard": r.get("hazard", ""),
                             "start_sec": r.get("start_sec", ""), "quality": "degraded360"})

    print("\nrows to add to labels.csv:")
    for nr in new_rows:
        print(f"{nr['clip']},{nr['hazard']},{nr['start_sec']},{nr['quality']}")

    if args.append and new_rows:
        with open(args.labels, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["clip", "hazard", "start_sec", "quality"])
            for nr in new_rows:
                w.writerow(nr)
        print(f"\nappended {len(new_rows)} rows to {args.labels}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
