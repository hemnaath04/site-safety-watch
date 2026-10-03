"""Self-contained tests for the Story eval harness. Run: python story/tests/test_eval.py

Uses the real watcher through --fake-vision --no-frames, so it needs no OpenCV, no clips and
no box. The fake client always reports blocked_exit, so every blocked clip is caught and every
clear clip is a false alarm. That is a deterministic check of the counting logic per setting,
not a measure of real accuracy. Needs Mithuna's watcher package in the working tree.
"""
from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from story.eval import run_eval, latency_for, setting_env  # noqa: E402
from story.validate_labels import validate_rows  # noqa: E402


def _write_labels(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["clip", "hazard", "start_sec", "quality"])
        for r in rows:
            w.writerow(r)


def test_matrix_counts_fake():
    with tempfile.TemporaryDirectory() as d:
        labels = Path(d) / "labels.csv"
        out = Path(d) / "numbers.json"
        _write_labels(labels, [
            ["01_blocked_exitA.mp4", "blocked_exit", "4", "phone"],
            ["02_blocked_exitA.mp4", "blocked_exit", "6", "phone"],
            ["03_clear_exitA.mp4", "none", "", "phone"],
            ["04_clear_exitA.mp4", "none", "", "phone"],
        ])
        numbers = run_eval(labels_path=labels, out_path=out, clips_dir=str(d),
                           fake=True, no_frames=True, settings=["baseline", "vote"],
                           repo_root=REPO_ROOT)
        assert numbers["settings_run"] == ["baseline", "vote"], numbers["settings_run"]
        for s in ("baseline", "vote"):
            ov = numbers["by_setting"][s]["overall"]
            assert ov["sample_size"] == 4, ov
            assert ov["caught"] == 2 and ov["missed"] == 0, ov
            assert ov["false_alarms"] == 2 and ov["true_clean"] == 0, ov
            assert ov["recall"] == 1.0 and ov["precision"] == 0.5, ov
            assert numbers["by_setting"][s]["by_quality"]["phone"]["caught"] == 2
        assert out.exists()
    print("ok: matrix counts per setting (fake)")


def test_latency_for():
    idx = {"a.mp4": [{"hazard": "blocked_exit", "frame_sec": 6.0},
                     {"hazard": "none", "frame_sec": 2.0}]}
    assert latency_for(idx, "a.mp4", 4.0, "baseline") == 2.0
    assert latency_for(idx, "missing.mp4", 4.0, "baseline") is None
    idx2 = {"a.mp4": [{"hazard": "blocked_exit", "frame_sec": 6.0, "setting": "vote"}]}
    assert latency_for(idx2, "a.mp4", 4.0, "baseline") is None   # setting filter excludes it
    assert latency_for(idx2, "a.mp4", 4.0, "vote") == 2.0
    print("ok: latency_for")


def test_setting_env():
    assert setting_env("baseline", None) == {}
    assert setting_env("enhance", None) == {"SSW_ENHANCE": "1"}
    assert setting_env("all", None) == {"SSW_ENHANCE": "1", "SSW_LOCATE": "1", "SSW_VOTE": "3/4"}
    assert "SSW_VERIFIER_URL" in setting_env("all+cosmos", "http://x")
    assert "SSW_VERIFIER_URL" not in setting_env("all+cosmos", None)
    print("ok: setting_env")


def test_validate_labels():
    header = ["clip", "hazard", "start_sec", "quality"]
    good = [{"clip": "a.mp4", "hazard": "blocked_exit", "start_sec": "4", "quality": "cctv_angle"},
            {"clip": "b.mp4", "hazard": "none", "start_sec": "", "quality": "phone"}]
    errors, warnings, summary = validate_rows(header, good)
    assert errors == [], errors
    assert summary["blocked"] == 1 and summary["clear"] == 1, summary

    bad = [{"clip": "a.mp4", "hazard": "fire", "start_sec": "4", "quality": "phone"},
           {"clip": "b.mp4", "hazard": "blocked_exit", "start_sec": "", "quality": "phone"},
           {"clip": "", "hazard": "none", "start_sec": "", "quality": "phone"}]
    errors, warnings, summary = validate_rows(header, bad)
    assert any("hazard must be one of" in e for e in errors), errors
    assert any("needs start_sec" in e for e in errors), errors
    assert any("empty clip" in e for e in errors), errors

    errors, _, _ = validate_rows(["clip", "hazard", "hazard_start_sec", "zone"], good)
    assert any("header must be" in e for e in errors), "old header should fail"
    print("ok: validate_labels")


def main():
    test_matrix_counts_fake()
    test_latency_for()
    test_setting_env()
    test_validate_labels()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
