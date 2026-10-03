# Site Safety Watch

An always-on safety agent that watches site cameras on one Dell Pro Max with GB10, spots a
blocked exit, and posts it to Slack with the evidence frame, the OSHA rule and a fix to approve.
All inference runs on the GB10. Raw video never leaves the box.

Built on Sat 2026-10-03 at the Dell x NVIDIA AI Hackathon, Boston. Nothing in this repo was
written before doors opened that day.

- `watcher/`: frame sampling, local vision check, de-duplication, SQLite store, `ssw` CLI
- `agent/`: OpenClaw skill and tools, Slack alert and disposition
- `story/`: labels, eval, numbers.json
- `data/`: clips, frames and the database (not committed)
- `plans/`: the masterplan and the scope of work (owners and frozen contracts)
