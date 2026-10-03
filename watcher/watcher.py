"""The watch loop: sample a clip, classify each frame, de-duplicate, store the event.

On a laptop run with --fake-vision (no OpenCV or box needed if you also pass --no-frames,
which drives the loop from the fake client alone). On the box Hemnaath runs it on real
clips against the local model.

Examples:
  python -m watcher.watcher --clip data/clips/01_blocked_exit.mp4 --zone exit_a --fake-vision
  python -m watcher.watcher --clip data/clips/01_blocked_exit.mp4 --zone exit_a
  python -m watcher.watcher --fake-vision --no-frames --zone exit_a   # logic smoke test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, dedup, rules, store, vision
from .sampler import utc_now


def _save_frame(jpeg_bytes, clip_name, when) -> str:
    config.ensure_dirs()
    stamp = when.strftime("%Y%m%dT%H%M%S")
    safe = Path(clip_name).stem or "cam"
    out = config.FRAMES_DIR / f"{safe}_{stamp}_{abs(hash(when)) % 10000}.jpg"
    out.write_bytes(jpeg_bytes or b"")
    return str(out.relative_to(config.REPO_ROOT))


def _handle(conn, client, jpeg_bytes, clip_name, zone, log):
    """Classify one frame and store a new event if it is a real, non-duplicate hazard."""
    try:
        event = client.classify(jpeg_bytes, zone)
    except Exception as exc:  # retry once, then skip
        try:
            event = client.classify(jpeg_bytes, zone)
        except Exception:
            log(f"skip: vision error: {exc}")
            return None
    if not rules.validate_event(event):
        log(f"skip: malformed event: {event}")
        return None
    if event["hazard"] == "none":
        return None
    if float(event["confidence"]) < config.MIN_CONFIDENCE:
        log(f"skip: low confidence {event['confidence']}")
        return None

    when = utc_now()
    if dedup.is_duplicate(conn, event["hazard"], zone, when):
        log(f"dup: {event['hazard']} in {zone} already open")
        return None

    frame_path = _save_frame(jpeg_bytes, clip_name, when)
    key = dedup.make_dedup_key(event["hazard"], zone, when, config.DEDUP_WINDOW_MIN)
    row = store.insert_event(
        conn, clip=clip_name, hazard=event["hazard"], zone=zone,
        confidence=event["confidence"], explanation=event.get("explanation", ""),
        frame_path=frame_path, dedup_key=key,
    )
    log(f"event {row['id']}: {row['hazard']} in {zone} ({row['confidence']})")
    return row


def run(clip, zone, fake=False, no_frames=False, interval=None):
    conn = store.connect()
    client = vision.get_vision(fake)

    def log(msg):
        print(msg, file=sys.stderr)

    created = []
    if no_frames:
        # Logic smoke test: drive the loop from the fake client with no video.
        row = _handle(conn, client, None, clip or "fake_cam", zone, log)
        if row:
            created.append(row)
    else:
        from .sampler import iter_frames
        for _sec, jpeg in iter_frames(clip, interval_sec=interval):
            row = _handle(conn, client, jpeg, clip, zone, log)
            if row:
                created.append(row)
    print(json.dumps(created))
    return created


def main(argv=None):
    p = argparse.ArgumentParser(description="Site Safety Watch watcher")
    p.add_argument("--clip", default="fake_cam", help="mp4 path or stream URL")
    p.add_argument("--zone", required=True, help="zone name from the clip config")
    p.add_argument("--fake-vision", action="store_true", help="use the canned client")
    p.add_argument("--no-frames", action="store_true",
                   help="drive from the fake client with no video (logic smoke test)")
    p.add_argument("--interval", type=float, default=None, help="seconds between frames")
    args = p.parse_args(argv)
    run(args.clip, args.zone, fake=args.fake_vision, no_frames=args.no_frames,
        interval=args.interval)


if __name__ == "__main__":
    main()
