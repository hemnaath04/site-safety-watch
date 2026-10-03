"""The ssw CLI: the seam between the watcher and the agent. Contract 0.5.

Every command prints JSON and nothing else (ssw pending prints the bare string NO_REPLY
when there is nothing new, which suits an openclaw cron that stays quiet).

  ssw events --status new
  ssw event <id>
  ssw rule <hazard>
  ssw mark-posted <id>
  ssw dispose <id> approved|false_alarm --by <slack_user>
  ssw pending
"""
from __future__ import annotations

import argparse
import json
import sys

from . import rules, store


def _out(obj):
    print(json.dumps(obj))


def _event_with_rule(event):
    r = rules.lookup_rule(event["hazard"])
    return {**event, "rule": f"{r['cite']}: {r['text']}", "fix": r["fix"]}


def main(argv=None):
    p = argparse.ArgumentParser(prog="ssw")
    sub = p.add_subparsers(dest="cmd", required=True)

    pe = sub.add_parser("events")
    pe.add_argument("--status", default="new")

    pget = sub.add_parser("event")
    pget.add_argument("id", type=int)

    pr = sub.add_parser("rule")
    pr.add_argument("hazard")

    pm = sub.add_parser("mark-posted")
    pm.add_argument("id", type=int)

    pd = sub.add_parser("dispose")
    pd.add_argument("id", type=int)
    pd.add_argument("status", choices=["approved", "false_alarm"])
    pd.add_argument("--by", required=True)

    sub.add_parser("pending")

    args = p.parse_args(argv)
    conn = store.connect()

    if args.cmd == "events":
        _out(store.events_by_status(conn, args.status))
        return
    if args.cmd == "event":
        ev = store.get_event(conn, args.id)
        if not ev:
            _out({"error": "not found", "id": args.id})
            sys.exit(1)
        _out(_event_with_rule(ev))
        return
    if args.cmd == "rule":
        r = rules.lookup_rule(args.hazard)
        _out({"cite": r["cite"], "text": r["text"], "fix": r["fix"]})
        return
    if args.cmd == "mark-posted":
        ev = store.mark_posted(conn, args.id)
        _out(ev or {"error": "not found", "id": args.id})
        return
    if args.cmd == "dispose":
        ev = store.dispose(conn, args.id, args.status, args.by)
        _out(ev or {"error": "not found", "id": args.id})
        return
    if args.cmd == "pending":
        new = store.events_by_status(conn, "new")
        if not new:
            print("NO_REPLY")
            return
        _out({"count": len(new),
              "events": [{"id": e["id"], "hazard": e["hazard"], "zone": e["zone"]}
                         for e in new]})
        return


if __name__ == "__main__":
    main()
