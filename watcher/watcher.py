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
from datetime import datetime
from pathlib import Path

from . import blur, config, dedup, motion, resolve, rules, store, vision, zones
from . import enhance as enhance_mod
from . import locate as locate_mod
from . import verifier, voting
from .sampler import now_local


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


def _log_decision(rec) -> None:
    """Append one per-frame decision to the decisions log (best effort)."""
    try:
        config.ensure_dirs()
        with open(config.DECISIONS_LOG, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass


def _seconds_between(start_iso, end_dt) -> float:
    """Seconds from an ISO timestamp to a datetime, never negative."""
    try:
        return max(0.0, (end_dt - datetime.fromisoformat(start_iso)).total_seconds())
    except (ValueError, TypeError):
        return 0.0


def _resolve_zone(conn, zone, jpeg_bytes, clip_name, do_blur, log) -> None:
    """Mark every open event in a zone resolved, with the clear time and a frame."""
    active = store.active_events(conn, zone)
    if not active:
        return
    when = now_local()
    resolved_ts = store.now_iso()
    frame_path = _save_frame(jpeg_bytes, clip_name, when, do_blur=do_blur)
    for ev in active:
        ttc = _seconds_between(ev["ts"], when)
        store.resolve_event(conn, ev["id"], resolved_ts=resolved_ts,
                            resolved_frame_path=frame_path, time_to_clear_sec=ttc)
        log(f"resolved {ev['id']}: {zone} clear, time to clear {ttc:.0f}s")


def _handle(conn, client, jpeg_bytes, clip_name, zone, log,
            voter=None, second_look=False, do_blur=True,
            enhance=False, locate=False, zone_box=None, verify=None, resolver=None):
    """Classify one frame and store a new event if it is a real, confirmed, non-duplicate
    hazard. Every frame is observed by the voter (when on) and logged to the decisions log.
    """
    vision_jpeg = jpeg_bytes
    transform = None
    if enhance and jpeg_bytes:
        vision_jpeg, transform = enhance_mod.enhance_jpeg(jpeg_bytes, zone_box)

    try:
        event = client.classify(vision_jpeg, zone)
    except Exception as exc:  # retry once, then treat as a miss
        try:
            event = client.classify(vision_jpeg, zone)
        except Exception:
            log(f"skip: vision error: {exc}")
            if voter is not None:
                voter.observe(zone, False)
            return None

    valid = rules.validate_event(event)
    present = (valid and event.get("hazard") not in (None, "none")
               and float(event.get("confidence", 0)) >= config.MIN_CONFIDENCE)

    box = event.get("box") if valid else None
    # If the frame was enhanced (cropped/upscaled), map the box back to original coords so
    # the overlap check, the stored box, the 3D highlight and the console overlay all agree.
    if box and transform:
        box = enhance_mod.untransform_box(box, transform)
    if present and locate and zone_box and box:
        if not locate_mod.in_zone(box, zone_box, config.LOCATE_MIN_OVERLAP):
            log(f"filtered: obstruction not in exit zone {zone}")
            present = False

    met = True
    if voter is not None:
        met = voter.observe(zone, present)

    if not valid:
        action = "malformed"
    elif not present:
        action = "no_hazard"
    elif not met:
        action = "voting"
    else:
        action = "candidate"

    _log_decision({
        "ts": store.now_iso(), "zone": zone, "clip": clip_name,
        "hazard": event.get("hazard") if valid else None,
        "confidence": event.get("confidence") if valid else None,
        "box": box, "present": present, "voted": met, "action": action,
    })

    # Auto-resolution: a clear check is an exit that is visible and not blocked. Two in a row
    # close the open events in the zone. A hazard or unreadable frame resets the streak.
    if resolver is not None:
        clear = valid and bool(event.get("exit_visible")) and event.get("hazard") == "none"
        if resolver.observe(zone, clear):
            _resolve_zone(conn, zone, jpeg_bytes, clip_name, do_blur, log)

    if not (valid and present and met):
        if action == "malformed":
            log(f"skip: malformed event: {event}")
        elif action == "voting":
            log(f"vote: holding {event.get('hazard')} in {zone}")
        return None

    hazard = event["hazard"]
    if second_look and not _confirm(client, vision_jpeg, zone, hazard, log):
        return None
    if verify is not None and not verify(vision_jpeg, zone):
        log(f"filtered: verifier rejected {hazard} in {zone}")
        return None

    when = now_local()
    if dedup.is_duplicate(conn, hazard, zone, when):
        log(f"dup: {hazard} in {zone} already open")
        return None

    frame_path = _save_frame(jpeg_bytes, clip_name, when, do_blur=do_blur)
    key = dedup.make_dedup_key(hazard, zone, when, config.DEDUP_WINDOW_MIN)
    row = store.insert_event(
        conn, clip=clip_name, hazard=hazard, zone=zone,
        confidence=event["confidence"], explanation=event.get("explanation", ""),
        frame_path=frame_path, dedup_key=key, box=box,
    )
    log(f"event {row['id']}: {hazard} in {zone} ({row['confidence']})")
    return row


def run(clip, zone=None, fake=False, no_frames=False, interval=None,
        stream=False, max_frames=None, motion_gate=False, second_look=False,
        do_blur=True, vote=None, enhance=None, locate=None, verifier_url=None,
        auto_resolve=None):
    conn = store.connect()
    client = vision.get_vision(fake)
    zone = zones.resolve_zone(clip, override=zone)
    zone_box = zones.exit_box(zone)
    gate = motion.MotionGate() if motion_gate else None

    # Accuracy switches: explicit arg wins, else the environment default.
    enhance = config.ENHANCE if enhance is None else enhance
    locate = config.LOCATE if locate is None else locate
    spec = voting.parse_vote(config.VOTE_SPEC if vote is None else vote)
    voter = voting.Voter(*spec) if spec else None
    vurl = config.VERIFIER_URL if verifier_url is None else verifier_url
    verify = verifier.CosmosVerifier(vurl).confirms if vurl else None
    auto_resolve = config.AUTO_RESOLVE if auto_resolve is None else auto_resolve
    resolver = resolve.Resolver() if auto_resolve else None

    def log(msg):
        print(msg, file=sys.stderr)

    kw = dict(voter=voter, second_look=second_look, do_blur=do_blur,
              enhance=enhance, locate=locate, zone_box=zone_box, verify=verify,
              resolver=resolver)

    created = []
    if no_frames:
        # Logic smoke test: drive the loop from the fake client with no video.
        row = _handle(conn, client, None, clip or "fake_cam", zone, log, **kw)
        if row:
            created.append(row)
    else:
        from .sampler import iter_frames
        for _sec, jpeg in iter_frames(clip, interval_sec=interval, stream=stream,
                                      max_frames=max_frames):
            if gate is not None and not gate.passed(jpeg):
                continue
            row = _handle(conn, client, jpeg, clip, zone, log, **kw)
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
    p.add_argument("--vote", default=None,
                   help="temporal voting, for example 3/4 (seen in 3 of the last 4 samples)")
    p.add_argument("--enhance", action="store_true",
                   help="crop to the exit zone, upscale and CLAHE the frame before the model")
    p.add_argument("--locate", action="store_true",
                   help="ask for the obstruction box and require it to overlap the exit zone")
    p.add_argument("--verifier-url", default=None,
                   help="second verifier (Cosmos) OpenAI-compatible URL, local host only")
    p.add_argument("--no-auto-resolve", action="store_true",
                   help="do not auto-resolve events after two clear checks in a row")
    args = p.parse_args(argv)
    run(args.clip, args.zone, fake=args.fake_vision, no_frames=args.no_frames,
        interval=args.interval, stream=args.stream, max_frames=args.max_frames,
        motion_gate=args.motion_gate, second_look=args.second_look,
        do_blur=not args.no_blur, vote=args.vote,
        enhance=True if args.enhance else None,
        locate=True if args.locate else None, verifier_url=args.verifier_url,
        auto_resolve=False if args.no_auto_resolve else None)


if __name__ == "__main__":
    main()
