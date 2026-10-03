"""Eval harness: run the watcher over every labelled clip, for each setting and quality level,
and write story/numbers.json.

Rahul owns this. For each setting it sets the matching env switches, runs the watcher on every
clip in a fresh database, reads the created events, and compares them to the ground truth in
labels.csv. It reports counts per setting and per quality level.

Settings (leader's plan):
  baseline    switches off
  enhance     SSW_ENHANCE=1
  locate      SSW_LOCATE=1
  vote        SSW_VOTE=3/4
  all         enhance + locate + vote
  all+cosmos  all + SSW_VERIFIER_URL set (skipped if no verifier url is given)

Per group it reports: sample_size, caught, missed, false_alarms (on clear clips), true_clean,
recall, precision, median seconds from start_sec to the detection.

Latency is read from data/decisions.jsonl when the watcher writes it (one JSON object per line
with at least {"clip","frame_sec","hazard"} and optionally "setting"). Counts work without it;
latency is null when it is absent.

Every number comes from a real run, nothing is invented. On a laptop run with --fake-vision to
check the harness (the fake client always reports blocked_exit, so clear clips become false
alarms by design). Hemnaath runs it for real on the box and sends numbers.json.

Examples:
  python -m story.eval --fake-vision --no-frames --settings baseline,vote --out numbers.fake.json
  python -m story.eval --settings all-settings --labels story/labels.csv --clips-dir data/clips --out story/numbers.json
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
POSITIVE = "blocked_exit"
DEFAULT_ZONE = "exitA"
LABEL_FIELDS = ["clip", "hazard", "start_sec", "quality"]
ALL_SETTINGS = ["baseline", "enhance", "locate", "vote", "all", "all+cosmos"]


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_labels(p):
    with open(p, newline="", encoding="utf-8") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def setting_env(name, verifier_url):
    """Env switches for a setting. The watcher must honor these (see team note)."""
    e = {}
    if name in ("enhance", "all", "all+cosmos"):
        e["SSW_ENHANCE"] = "1"
    if name in ("locate", "all", "all+cosmos"):
        e["SSW_LOCATE"] = "1"
    if name in ("vote", "all", "all+cosmos"):
        e["SSW_VOTE"] = "3/4"
    if name == "all+cosmos" and verifier_url:
        e["SSW_VERIFIER_URL"] = verifier_url
    return e


def _unlink(p):
    try:
        p.unlink()
    except OSError:
        pass


def run_watcher_on_clip(clip_path, zone, env_over, *, repo_root, fake, no_frames, interval):
    """Run the watcher on one clip in a fresh database. Returns (events, error)."""
    key = abs(hash((clip_path, tuple(sorted(env_over.items()))))) % 1000000
    tmp_db = Path(tempfile.gettempdir()) / f"ssw_eval_{os.getpid()}_{key}.db"
    env = dict(os.environ)
    env["SSW_DB"] = str(tmp_db)
    env.update(env_over)
    cmd = [sys.executable, "-m", "watcher.watcher", "--clip", str(clip_path), "--zone", zone]
    if fake:
        cmd.append("--fake-vision")
    if no_frames:
        cmd.append("--no-frames")
    if interval is not None:
        cmd += ["--interval", str(interval)]
    try:
        proc = subprocess.run(cmd, cwd=str(repo_root), env=env,
                              capture_output=True, text=True, timeout=600)
    except Exception as exc:
        _unlink(tmp_db)
        return [], f"run failed: {exc}"
    _unlink(tmp_db)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-1:]
        return [], f"watcher exit {proc.returncode}: {' '.join(tail)}"
    out = (proc.stdout or "").strip()
    if not out:
        return [], None
    try:
        events = json.loads(out.splitlines()[-1])
    except json.JSONDecodeError as exc:
        return [], f"bad watcher output: {exc}"
    return (events if isinstance(events, list) else []), None


def load_decisions(path):
    """Index data/decisions.jsonl by clip. Each line: {clip, frame_sec, hazard, setting?}."""
    idx = {}
    p = Path(path)
    if not p.exists():
        return idx
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            idx.setdefault(rec.get("clip"), []).append(rec)
    return idx


def latency_for(idx, clip, start_sec, setting):
    """Seconds from start_sec to the first blocked_exit decision for this clip, or None."""
    if start_sec is None:
        return None
    secs = []
    for r in idx.get(clip, []):
        if r.get("hazard") != POSITIVE:
            continue
        if r.get("setting") and r.get("setting") != setting:
            continue
        fs = r.get("frame_sec")
        if isinstance(fs, (int, float)):
            secs.append(float(fs))
    if not secs:
        return None
    lat = min(secs) - start_sec
    return round(lat, 2) if lat >= 0 else 0.0


def _counts(runs):
    tp = fn = fp = tn = 0
    lats = []
    for r in runs:
        if r.get("error"):
            continue
        if r["label"] != "none":
            if r["detected"]:
                tp += 1
                if r.get("latency_sec") is not None:
                    lats.append(r["latency_sec"])
            else:
                fn += 1
        else:
            if r["detected"]:
                fp += 1
            else:
                tn += 1
    hz, cl = tp + fn, fp + tn
    return {
        "sample_size": tp + fn + fp + tn,
        "blocked_clips": hz,
        "clear_clips": cl,
        "caught": tp,
        "missed": fn,
        "false_alarms": fp,
        "true_clean": tn,
        "recall": round(tp / hz, 3) if hz else None,
        "precision": round(tp / (tp + fp), 3) if (tp + fp) else None,
        "median_latency_sec": round(statistics.median(lats), 2) if lats else None,
    }


def evaluate(rows, *, repo_root, clips_dir, fake, no_frames, interval,
             settings, zone, verifier_url, decisions_idx):
    per_run, errors = [], []
    for sname in settings:
        env_over = setting_env(sname, verifier_url)
        for r in rows:
            clip = (r.get("clip") or "").strip()
            label = (r.get("hazard") or "").strip() or "none"
            quality = (r.get("quality") or "").strip() or "unknown"
            raw = (r.get("start_sec") or "").strip()
            start_sec = float(raw) if raw else None
            clip_path = clip if no_frames else str(Path(clips_dir) / clip)

            events, err = run_watcher_on_clip(clip_path, zone, env_over, repo_root=repo_root,
                                              fake=fake, no_frames=no_frames, interval=interval)
            det = sorted({e.get("hazard") for e in events
                          if e.get("hazard") and e.get("hazard") != "none"})
            detected = len(det) > 0
            rec = {"setting": sname, "clip": clip, "quality": quality, "label": label,
                   "detected": detected, "detected_hazards": det}
            if err:
                rec["result"] = "error"
                rec["error"] = err
                errors.append({"setting": sname, "clip": clip, "error": err})
            else:
                rec["latency_sec"] = latency_for(decisions_idx, clip, start_sec, sname) if detected else None
                if label != "none":
                    rec["result"] = "caught" if detected else "missed"
                else:
                    rec["result"] = "false_alarm" if detected else "true_clean"
            per_run.append(rec)
    return per_run, errors


def run_eval(*, labels_path, out_path, clips_dir, fake=False, no_frames=False, interval=None,
             settings=None, zone=DEFAULT_ZONE, verifier_url=None, decisions_path=None,
             repo_root=REPO_ROOT):
    rows = read_labels(Path(labels_path))
    settings = list(settings or ["baseline"])
    cosmos_skipped = False
    if "all+cosmos" in settings and not verifier_url:
        settings = [s for s in settings if s != "all+cosmos"]
        cosmos_skipped = True
    decisions_path = decisions_path or (Path(clips_dir).parent / "decisions.jsonl")
    decisions_idx = load_decisions(decisions_path)

    per_run, errors = evaluate(rows, repo_root=repo_root, clips_dir=clips_dir, fake=fake,
                               no_frames=no_frames, interval=interval, settings=settings,
                               zone=zone, verifier_url=verifier_url, decisions_idx=decisions_idx)
    qualities = sorted({r["quality"] for r in per_run})
    by_setting = {}
    for sname in settings:
        runs = [r for r in per_run if r["setting"] == sname]
        by_setting[sname] = {
            "overall": _counts(runs),
            "by_quality": {q: _counts([r for r in runs if r["quality"] == q]) for q in qualities},
        }
    numbers = {
        "generated_at": _now_iso(),
        "mode": "fake-vision (laptop, harness check, not real accuracy)" if fake else "real (box, local vLLM)",
        "settings_run": settings,
        "qualities_seen": qualities,
        "decisions_file": str(decisions_path) if Path(decisions_path).exists() else None,
        "latency_note": ("seconds from start_sec to the first blocked_exit decision in "
                         "data/decisions.jsonl; null when that file is absent"),
        "cosmos_skipped": cosmos_skipped,
        "by_setting": by_setting,
        "errors": errors,
        "per_run": per_run,
        "notes": ("Counts come from running the watcher on each clip in a fresh database, once "
                  "per setting. State the sample size next to every rate. In fake-vision mode "
                  "every clip reports blocked_exit, so clear clips become false alarms by "
                  "design; this only checks the harness."),
    }
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(numbers, indent=2) + "\n", encoding="utf-8")
    return numbers


def main(argv=None):
    p = argparse.ArgumentParser(description="SSW eval harness (Story): settings x quality matrix")
    p.add_argument("--labels", default=str(REPO_ROOT / "story" / "labels.csv"))
    p.add_argument("--out", default=str(REPO_ROOT / "story" / "numbers.json"))
    p.add_argument("--clips-dir", default=str(REPO_ROOT / "data" / "clips"))
    p.add_argument("--settings", default="baseline",
                   help="comma list (baseline,enhance,locate,vote,all,all+cosmos) or 'all-settings'")
    p.add_argument("--zone", default=DEFAULT_ZONE)
    p.add_argument("--verifier-url", default=os.environ.get("SSW_VERIFIER_URL"))
    p.add_argument("--decisions", default=None, help="path to decisions.jsonl (default data/decisions.jsonl)")
    p.add_argument("--fake-vision", action="store_true")
    p.add_argument("--no-frames", action="store_true")
    p.add_argument("--interval", type=float, default=None)
    a = p.parse_args(argv)
    settings = ALL_SETTINGS if a.settings == "all-settings" else [s.strip() for s in a.settings.split(",") if s.strip()]
    numbers = run_eval(labels_path=Path(a.labels), out_path=Path(a.out), clips_dir=a.clips_dir,
                       fake=a.fake_vision, no_frames=a.no_frames, interval=a.interval,
                       settings=settings, zone=a.zone, verifier_url=a.verifier_url,
                       decisions_path=a.decisions)
    print(json.dumps({"settings_run": numbers["settings_run"],
                      "qualities_seen": numbers["qualities_seen"],
                      "by_setting_overall": {k: v["overall"] for k, v in numbers["by_setting"].items()}},
                     indent=2))
    print("wrote", a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
