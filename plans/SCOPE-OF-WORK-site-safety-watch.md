# Site Safety Watch: Scope of Work (3 person build) - FINAL

Locked Sat 2026-10-03 11:43 by the captain. Goes with `plans/MASTERPLAN-site-safety-watch.md`.
Where this file and the masterplan disagree, the masterplan wins; tell Hemnaath.
People: Hemnaath (lead, Box + Agent), Mithuna (Watcher), Rahul (Story).
Rule reminder: all inference on the box, nothing from Canary Pact, fresh repo, no AI
attribution, no em dashes, OpenClaw required (we run it through NemoClaw + OpenShell).

**Completion rule (from the masterplan):** one hazard, blocked exit, end to end first. Clip to
local vision to de-duplicated event to Slack to human disposition to a stored record. Nothing
else starts until that loop has been recorded once.

---

## 0. Shared contracts (frozen at the lock; change only with all three agreeing)

### 0.1 Event JSON (what the vision call must return; the watcher validates it)
```json
{
  "hazard": "blocked_exit | none",
  "zone": "exit_a",
  "confidence": 0.0,
  "explanation": "one sentence: what in the frame is blocking the exit",
  "box": [0, 0, 0, 0]
}
```
Later hazards (`spill`, `trip_cable`) are added to the enum only after Gate 2.
`zone` comes from the clip's camera config, not from the model.
`box` is optional (post-lock, for LOCATE): the obstruction box `[x, y, width, height]` in
pixels, or `null`. The watcher accepts events with or without it.

Post-lock, the model is asked for the raw schema `{exit_visible, blocked, box, confidence,
explanation}`, enforced by vLLM guided decoding at temperature 0 so the reply always parses.
The vision client maps it to the event above: `blocked_exit` when an exit is both visible
and blocked, else `none`. Timestamps are stored in local time.

### 0.2 SQLite schema (`data/ssw.db`, owned by Mithuna, the single source of truth)
```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY,
  ts TEXT,               -- ISO time the hazard was first seen
  clip TEXT,             -- source clip or camera name
  hazard TEXT,
  zone TEXT,
  confidence REAL,
  explanation TEXT,
  frame_path TEXT,       -- evidence frame on disk (raw video never leaves the box)
  dedup_key TEXT,        -- hazard + zone + time bucket
  status TEXT,           -- new | posted | approved | false_alarm | resolved
  disposition_by TEXT,   -- Slack user who approved or rejected
  disposition_ts TEXT,
  box TEXT,              -- optional (post-lock, LOCATE): JSON [x,y,w,h] or null
  resolved_ts TEXT,      -- post-lock, auto-resolution: when the zone went clear
  resolved_frame_path TEXT,  -- the clear evidence frame
  time_to_clear_sec REAL,    -- measured seconds from first seen to resolved
  resolved_announced INTEGER DEFAULT 0  -- 1 once the agent has posted the resolution
);
```
A work order is this row with status `approved`; there is no second table or service.
The columns after `disposition_ts` are nullable and added by a safe migration, so older
databases keep working. Auto-resolution (post-lock): after two clear checks in a row in a
zone, open events there move to `resolved` with the time, a frame and the time to clear.

### 0.3 Rule table (plain table in code, not the model)
```
blocked_exit -> 29 CFR 1910.37: exit routes must be free and unobstructed
                fix: "Move the obstruction out of the exit route and tag the zone."
spill        -> 29 CFR 1910.22 (after Gate 2 only)
trip_cable   -> 29 CFR 1910.22 (after Gate 2 only)
```
Verify each exact paragraph on osha.gov before it goes on a slide.

### 0.4 Vision endpoint (live since 11:34, measured)
- `http://127.0.0.1:8000/v1/chat/completions` on the box, OpenAI compatible.
- Model name `nvidia/Qwen3.6-35B-A3B-NVFP4`. Send `"chat_template_kwargs": {"enable_thinking": false}`.
- Image as `{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}`.
- Measured: about 1.0 s warm per 960x640 image, 653 prompt tokens. Working example on the box:
  `~/smoke/vision_smoke.py`.
- Only Hemnaath connects to the box (see "Box access" below). On laptops, code uses a fake
  vision client with the same interface (returns canned Event JSON). Real calls happen only
  on the box. Never point anything at a cloud model, not even for testing.

### 0.5 The `ssw` CLI (the seam between Watcher and Agent; Mithuna builds, Hemnaath calls)
Every command prints JSON and nothing else.
```
ssw events --status new          -> [event, ...]
ssw event <id>                   -> event + {"rule": ..., "fix": ...}
ssw rule <hazard>                -> {"cite": ..., "text": ..., "fix": ...}
ssw mark-posted <id>             -> event
ssw dispose <id> approved|false_alarm --by <slack_user>  -> event
ssw pending                      -> "NO_REPLY" if nothing new, else a short summary
ssw pending-resolved             -> "NO_REPLY" if none, else resolved events not yet announced
ssw mark-resolved-announced <id> -> event
```
Until Mithuna's store exists, Hemnaath builds against a fake event inserted by hand.
Resolution (post-lock): `pending-resolved` returns events that just went clear (with
`time_to_clear_sec`, `resolved_ts`, `resolved_frame_path`); the agent posts the all-clear and
calls `mark-resolved-announced` so it posts once.

---

## Box access: Hemnaath only

Only Hemnaath connects to the GB10. Mithuna and Rahul never SSH in, tunnel, or copy files to it.
Everything that touches the box goes through Hemnaath:

| You want to | Do this | Hemnaath then |
|---|---|---|
| Run code on the box | push to the shared repo (or AirDrop a zip) and message Hemnaath | syncs it to `~/site-safety-watch` on the box, runs it, sends back the log |
| Test the vision prompt for real | send the prompt text + 1 to 3 frames | runs it against the box's model, sends back the JSON and the latency |
| Get clips onto the box | AirDrop the mp4 files + `labels.csv` | copies them to `data/clips/` on the box |
| Run the replay or the eval | hand over the script and the exact command | runs it in tmux on the box, sends back `numbers.json` and logs |
| See the Slack alert | watch #safety | nothing to do |

Code lives in the shared repo `site-safety-watch` (one folder each: `watcher/`, `agent/`,
`story/`). Hemnaath keeps the box copy in sync. Commits carry no AI attribution.

---

## 1. HEMNAATH (Lead): Box + Agent

### Mission
Stand up the box and the agent. Own integration, the lock, and the pitch.

### Build list, in order
Box (critical path):
1. DONE 11:25: models and the vLLM image copied from the SSD, all checksums OK.
2. DONE 11:36: vLLM with vision on port 8000; image in, JSON out, latency logged.
3. NemoClaw install (brings OpenClaw and OpenShell), pointed at our vLLM ("Existing vLLM").
4. Slack app (manifest ready), tokens stored only on the box, bot answers in #safety.
5. Decide by 13:15 where the agent's tools run: inside the sandbox (policy or shared mount
   for `ssw`) or OpenClaw on the host. Write the decision in MEMORY.md.
Box operator for the team (all box access is yours):
- Sync teammates' code from the repo to `~/site-safety-watch` on the box and run it.
- Run Mithuna's prompts on real frames and send back JSON and latency.
- Copy Rahul's clips and labels to `data/clips/`; run the replay and the eval in tmux; send
  back `numbers.json`, logs, unified memory in use and watts.
- Keep long jobs in tmux on the box; keep MEMORY.md current.
Agent:
6. OpenClaw skill with the core tools over the `ssw` CLI: list new events, get event, look up
   rule, set disposition. That is all for the core.
7. New-event check: `openclaw cron --every 1m` calling `ssw pending` (quiet when nothing new).
8. Alert in #safety: hazard, zone, rule, fix, evidence frame, and the disposition action.
   Buttons if they work by 15:30; otherwise text commands `approve <id>` / `false-alarm <id>`.
   If image upload from OpenClaw fails, post the text plus the event ID and show the frame
   beside Slack in the video.
9. Disposition writes back through `ssw dispose` and the agent replies with ID and status.

### Stretch (only after the core loop is recorded; pick at most two as a team)
Q&A over the event log, daily digest on cron, camera-based resolution check, OpenShell refusal
on screen, offline queue.

### Gates
- Gate 1: image in, Event JSON out (passed 11:36); bot answers in Slack.
- Gate 2 (with Mithuna): a clip produces a real Slack alert and the disposition is stored.

---

## 2. MITHUNA (Watcher): perception pipeline and the store

### Mission
Turn a video stream into clean, de-duplicated hazard events in the store, and expose them
through the `ssw` CLI.

### Build list, in order (you work on your laptop; Hemnaath runs it on the box)
1. Frame sampler: read an mp4 (Rahul's clips) and take one frame every N seconds (start
   with 2). Downscale to about 960 px wide. Later the same code reads the replay stream.
2. Vision call (0.4) with the blocked-exit checklist; parse and validate Event JSON (0.1).
   Malformed JSON: retry once, then log and skip. Make the endpoint URL a setting, and add a
   `--fake-vision` mode that returns canned Event JSON so you can test on your laptop. Send
   your prompt and a few frames to Hemnaath to try on the real model early.
3. De-duplication: same hazard + same zone within N minutes is one event (`dedup_key`).
4. Event store (0.2): write confirmed events, save the evidence frame to `data/frames/`.
5. Rule table (0.3) in code.
6. `ssw` CLI (0.5). This is the seam; ship it early, even with fake data.

### Stretch (after Gate 2, only if the eval shows the need)
Second look on candidates (cuts false alarms), motion gate (fewer model calls), face blur.
Face blur becomes required if any frame with a visible face would be posted.

### Gates
- Gate 2 (with Hemnaath): a clip in produces a stored event that becomes a Slack alert.
- Gate 3 (with Rahul): the watcher runs clean over all labelled clips for the eval.

### Risks you own
Model misses or invents blocked exits (tune the prompt on Rahul's clips, add the second look);
too slow (lower resolution, sample less often; the demo needs reliable detection, not frame rate).

---

## 3. RAHUL (Story): data, numbers, and everything the judges see

### Mission
Create the data, measure the system honestly, and produce the submission.

### Build list, in order
1. Film 8 clips (10 to 20 s each) by 13:00 in our room and corridor: 4 with an exit blocked
   (cart, boxes, chair stack), 4 clean (same door, clear). No strangers' faces; people walk out
   of frame before the hazard is left alone. Add up to 15 clips later if time allows.
2. `labels.csv`: clip, hazard or none, second the hazard starts. Ground truth for every number.
3. AirDrop the clips and `labels.csv` to Hemnaath, who puts them on the box.
4. Replay: write the command (`ffmpeg -re -stream_loop -1 -i clip.mp4 ...`, labelled on screen
   as replay) and agree the stream URL with Mithuna. Hemnaath runs it on the box.
5. Eval script: write it to run the watcher over all labelled clips and produce
   `numbers.json` with counts: caught, missed, false alarms on clean clips, sample size, and
   seconds from hazard to alert. Test it on your laptop with the watcher's `--fake-vision` mode;
   Hemnaath runs the real eval on the box and sends you `numbers.json`, plus unified memory in
   use and watts if we report them.
6. Demo video, 2 to 3 minutes, story beats from masterplan section 3. Record the Gate 2 run as
   a backup.
7. Five slides at a public link. Every number from `numbers.json` or labelled an assumption.
8. README and writeup; submit on BuilderBase.

### Gates
- 8 labelled clips by 13:00 (the others need them to test).
- Gate 3: numbers.json from the eval over all labelled clips.

---

## 4. Who needs what from whom

- Rahul gives clips + labels to Mithuna and Hemnaath early (13:00); Hemnaath puts them on the box.
- Hemnaath runs Mithuna's prompt on the real model on request (the endpoint is live now).
- Mithuna gives the `ssw` CLI + event store to Hemnaath (through the repo).
- Hemnaath gives the working Slack agent to Rahul for filming the video.
- Mithuna gives the runnable watcher to Rahul; Rahul gives the eval script to Hemnaath, who
  runs it on the box and returns `numbers.json`.

## 5. The gates (everyone aligns here)

- Gate 1 (by 12:45): box up and image to JSON (done 11:36), bot in Slack.
- Gate 2 (by 14:30): a clip to a Slack alert end to end with a stored disposition. Record backup.
- Gate 3 (by 15:30): numbers.json from the eval on all labelled clips.
- 15:30 hard fallback deadline (text commands instead of buttons; event ID instead of image).
- 15:30 to 16:15 record the full core demo. Feature freeze 17:00. Submit by 18:00. Slides by
  19:00. Before returning the box at 19:00: `sudo rm /etc/sudoers.d/90-hackathon`.

---

## 6. Changes after the lock (captain, 12:20 to 13:15)

| Person | New work | Where |
|---|---|---|
| Hemnaath | Box ops for everything; Cosmos-Reason2-2B server on port 8001; 3D scene service running on the box; console (`agent/viewer/`) with Codex | `agent/`, the box |
| Mithuna | Accuracy switches `SSW_ENHANCE`, `SSW_LOCATE`, `SSW_VOTE`, `SSW_VERIFIER_URL`; `zones.json` with auto-calibrated exit zones; nullable `box` column on events (she edits section 0 in her PR); per-frame log `data/decisions.jsonl` | `watcher/` |
| Rahul | CCTV-angle, dim and degraded 360p clips with `quality` in `labels.csv`; `story/eval.py` comparing baseline, enhance, locate, vote, all, all+cosmos; "Built on NVIDIA Cosmos" on slides and README | `story/` |

Drop deadlines: the 3D view and the Cosmos verifier are cut at 16:00 if they are not reliable,
so the 15:30 to 16:15 recording uses whatever is solid.
