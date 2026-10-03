"""Fake `ssw` CLI implementing scope section 0.5 against a JSON file.

State path comes from env SSW_FAKE_DB (default /tmp/ssw_fake.json). Prints JSON only.
Errors print {"error": ...} and exit non-zero; an unknown id uses error "not_found".
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules import get_rule  # noqa: E402

STATUSES = ("new", "posted", "approved", "false_alarm")
DISPOSITIONS = ("approved", "false_alarm")


def _event(id_, ts, zone, confidence, explanation, status, by=None, by_ts=None):
    return {
        "id": id_,
        "ts": ts,
        "clip": f"cam_{zone}",
        "hazard": "blocked_exit",
        "zone": zone,
        "confidence": confidence,
        "explanation": explanation,
        "frame_path": f"data/frames/event_{id_}.jpg",
        "dedup_key": f"blocked_exit:{zone}:{ts[:15]}",
        "status": status,
        "disposition_by": by,
        "disposition_ts": by_ts,
    }


def seed() -> list[dict]:
    return [
        _event(1, "2026-10-03T12:05:00", "exit_a", 0.91,
               "A stack of boxes sits in front of the exit door.", "new"),
        _event(2, "2026-10-03T12:10:00", "exit_b", 0.84,
               "A pallet jack is parked across the exit route.", "posted"),
        _event(3, "2026-10-03T11:40:00", "exit_a", 0.88,
               "A cart is left in the exit corridor.", "approved",
               "U000FAKE", "2026-10-03T11:45:00"),
    ]


def db_path() -> Path:
    return Path(os.environ.get("SSW_FAKE_DB", "/tmp/ssw_fake.json"))


def load() -> list[dict]:
    path = db_path()
    if not path.exists():
        events = seed()
        save(events)
        return events
    return json.loads(path.read_text())


def save(events: list[dict]) -> None:
    path = db_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(events, indent=2))
    tmp.replace(path)


def out(obj) -> None:
    print(json.dumps(obj))


def fail(error: str, code: int = 1) -> None:
    out({"error": error})
    sys.exit(code)


def find(events: list[dict], id_: int) -> dict:
    for ev in events:
        if ev["id"] == id_:
            return ev
    fail("not_found")


def main(argv: list[str]) -> None:
    p = argparse.ArgumentParser(prog="ssw")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("events")
    s.add_argument("--status", choices=STATUSES, required=True)
    s = sub.add_parser("event")
    s.add_argument("id", type=int)
    s = sub.add_parser("rule")
    s.add_argument("hazard")
    s = sub.add_parser("mark-posted")
    s.add_argument("id", type=int)
    s = sub.add_parser("dispose")
    s.add_argument("id", type=int)
    s.add_argument("disposition", choices=DISPOSITIONS)
    s.add_argument("--by", required=True)
    sub.add_parser("pending")

    try:
        args = p.parse_args(argv)
    except SystemExit:
        fail("bad_arguments", 2)

    if args.cmd == "rule":
        rule = get_rule(args.hazard)
        if rule is None:
            fail("not_found")
        out(rule)
        return

    events = load()
    if args.cmd == "events":
        out([e for e in events if e["status"] == args.status])
    elif args.cmd == "event":
        ev = dict(find(events, args.id))
        rule = get_rule(ev["hazard"]) or {}
        ev["rule"] = f"{rule['cite']}: {rule['text']}" if rule else None
        ev["fix"] = rule.get("fix")
        out(ev)
    elif args.cmd == "mark-posted":
        ev = find(events, args.id)
        ev["status"] = "posted"
        save(events)
        out(ev)
    elif args.cmd == "dispose":
        ev = find(events, args.id)
        ev["status"] = args.disposition
        ev["disposition_by"] = args.by
        ev["disposition_ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save(events)
        out(ev)
    elif args.cmd == "pending":
        new = [e for e in events if e["status"] == "new"]
        if not new:
            out("NO_REPLY")
        else:
            out("\n".join(f"#{e['id']} {e['hazard']} at {e['zone']} ({e['ts']})" for e in new))


if __name__ == "__main__":
    main(sys.argv[1:])
