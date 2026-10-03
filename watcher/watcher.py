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

from . import blur, config, dedup, motion, rules, store, vision, zones
from .sampler import utc_now


def _save_frame(jpeg_bytes, clip_name, when, do_blur=True) -> str:
    config.ensure_dirs()
    if do_blur and jpeg_bytes:
        jpeg_bytes = blur.blur_jpeg(jpeg_bytes)
    stamp = when.strftime("%Y%m%dT%H%M%S")
    safe = Path(clip_name).stem or "cam"
    out = config.FRAMES_DIR / f"{safe}_{stamp}_{abs(hash(when)) % 10000}.jpg"
    out.write_bytes(jpeg_bytes or b"")
    return str(out.relative_to(config.REPO_ROOT))


def _confirm(client, jpeg_bytes, zone, hazard, log):
    """Second look: re-ask with a stricter prompt; return True only if it still holds."""
    prompt = rules.SECOND_LOOK_PROMPT.format(hazard=hazard)
    try:
        ev2 = client.classify(jpeg_bytes, zone, prompt=prompt)
    except Exception as exc:
        log(f"skip: second look error: {exc}")
        return False
    if not rules.validate_event(ev2):
        log(f"skip: second look malformed: {ev2}")
        return False
    if ev2["hazard"] != hazard or float(ev2["confidence"]) < config.MIN_CONFIDENCE:
        log(f"filtered: second look did not confirm {hazard}")
        return False
    return True


def _handle(conn, client, jpeg_bytes, clip_name, zone, log,
            second_look=False, do_blur=True):
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

    if second_look and not _confirm(client, jpeg_bytes, zone, event["hazard"], log):
        return None

    when = utc_now()
    if dedup.is_duplicate(conn, event["hazard"], zone, when):
        log(f"dup: {event['hazard']} in {zone} already open")
        return None

    frame_path = _save_frame(jpeg_bytes, clip_name, when, do_blur=do_blur)
    key = dedup.make_dedup_key(event["hazard"], zone, when, config.DEDUP_WINDOW_MIN)
    row = store.insert_event(
        conn, clip=clip_name, hazard=event["hazard"], zone=zone,
        confidence=event["confidence"], explanation=event.get("explanation", ""),
        frame_path=frame_path, dedup_key=key,
    )
    log(f"event {row['id']}: {row['hazard']} in {zone} ({row['confidence']})")
    return row


def run(clip, zone=None, fake=False, no_frames=False, interval=None,
        stream=False, max_frames=None, motion_gate=False, second_look=False,
        do_blur=True):
    conn = store.connect()
    client = vision.get_vision(fake)
    zone = zones.resolve_zone(clip, override=zone)
    gate = motion.MotionGate() if motion_gate else None

    def log(msg):
        print(msg, file=sys.stderr)

    created = []
    if no_frames:
        # Logic smoke test: drive the loop from the fake client with no video.
        row = _handle(conn, client, None, clip or "fake_cam", zone, log,
                      second_look=second_look, do_blur=do_blur)
        if row:
            created.append(row)
    else:
        from .sampler import iter_frames
        for _sec, jpeg in iter_frames(clip, interval_sec=interval, stream=stream,
                                      max_frames=max_frames):
            if gate is not None and not gate.passed(jpeg):
                continue
            row = _handle(conn, client, jpeg, clip, zone, log,
                          second_look=second_look, do_blur=do_blur)
            if row:
                created.append(row)
    print(json.dumps(created))
    return created


def main(argv=None):
    p = argparse.ArgumentParser(description="Site Safety Watch watcher")
    p.add_argument("--clip", default="fake_cam", help="mp4 path or stream URL")
    p.add_argument("--zone", default=None,
                   help="override the zone; otherwise resolved from the clip name or config")
    p.add_argument("--fake-vision", action="store_true", help="use the canned client")
    p.add_argument("--no-frames", action="store_true",
                   help="drive from the fake client with no video (logic smoke test)")
    p.add_argument("--interval", type=float, default=None, help="seconds between frames")
    p.add_argument("--stream", action="store_true",
                   help="treat the source as a live replay and reconnect on a drop")
    p.add_argument("--max-frames", type=int, default=None,
                   help="stop after this many sampled frames (eval or bounded capture)")
    p.add_argument("--motion-gate", action="store_true",
                   help="skip the vision call when the scene has not changed")
    p.add_argument("--second-look", action="store_true",
                   help="confirm a candidate with a stricter re-ask before storing it")
    p.add_argument("--no-blur", action="store_true",
                   help="do not blur faces on the saved frame (use only on clips with no people)")
    args = p.parse_args(argv)
    run(args.clip, args.zone, fake=args.fake_vision, no_frames=args.no_frames,
        interval=args.interval, stream=args.stream, max_frames=args.max_frames,
        motion_gate=args.motion_gate, second_look=args.second_look,
        do_blur=not args.no_blur)


if __name__ == "__main__":
    main()
