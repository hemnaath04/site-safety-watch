"""Validate story/labels.csv, the ground truth for every number.

Schema (leader's plan): clip,hazard,start_sec,quality
  hazard  = blocked_exit or none
  start_sec = second the object is left alone (blank for a clean clip)
  quality = phone, cctv_angle, dim or degraded360

Prints a summary and exits nonzero on a hard error. Rahul runs this after labelling.
Usage: python -m story.validate_labels --labels story/labels.csv
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIELDS = ["clip", "hazard", "start_sec", "quality"]
HAZARDS = ["blocked_exit", "none"]
QUALITIES = ["phone", "cctv_angle", "dim", "degraded360"]


def validate_rows(header, rows):
    """Return (errors, warnings, summary). errors block the eval, warnings do not."""
    errors, warnings = [], []
    if list(header) != FIELDS:
        errors.append(f"header must be {FIELDS}, found {list(header)}")
        return errors, warnings, {}

    seen = set()
    hazard_n = clean_n = 0
    by_quality = {}
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        clip = (r.get("clip") or "").strip()
        hazard = (r.get("hazard") or "").strip()
        start = (r.get("start_sec") or "").strip()
        quality = (r.get("quality") or "").strip()

        if not clip:
            errors.append(f"row {i}: empty clip")
        elif clip in seen:
            errors.append(f"row {i}: duplicate clip {clip}")
        else:
            seen.add(clip)
        if hazard not in HAZARDS:
            errors.append(f"row {i}: hazard must be one of {HAZARDS}, found '{hazard}'")
        if not quality:
            errors.append(f"row {i}: empty quality")
        elif quality not in QUALITIES:
            warnings.append(f"row {i}: unusual quality '{quality}', expected one of {QUALITIES}")
        by_quality[quality] = by_quality.get(quality, 0) + 1

        if hazard == "none":
            clean_n += 1
        elif hazard in HAZARDS:
            hazard_n += 1
            if not start:
                errors.append(f"row {i}: hazard row needs start_sec")
            else:
                try:
                    if float(start) < 0:
                        errors.append(f"row {i}: start_sec must be >= 0")
                except ValueError:
                    errors.append(f"row {i}: start_sec must be a number, found '{start}'")

    total = hazard_n + clean_n
    if total < 8:
        warnings.append(f"only {total} clips, the Gate asks for at least 8 (leader wants 5+ blocked, 5+ clear)")
    if hazard_n < 5:
        warnings.append(f"only {hazard_n} blocked clips, leader wants 5 or more")
    if clean_n < 5:
        warnings.append(f"only {clean_n} clear clips, leader wants 5 or more")
    summary = {"total": total, "blocked": hazard_n, "clear": clean_n, "by_quality": by_quality}
    return errors, warnings, summary


def main(argv=None):
    p = argparse.ArgumentParser(description="Validate labels.csv")
    p.add_argument("--labels", default=str(REPO_ROOT / "story" / "labels.csv"))
    args = p.parse_args(argv)
    path = Path(args.labels)
    if not path.exists():
        print(f"labels file not found: {path}")
        return 1
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = reader.fieldnames or []
        rows = [dict(r) for r in reader]
    errors, warnings, summary = validate_rows(header, rows)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    print(f"summary: {summary}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
