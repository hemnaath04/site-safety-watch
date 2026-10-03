# Masterplan: Site Safety Watch

Status: **LOCKED, FINAL** Sat 2026-10-03 11:43 by the captain ("make it final, let's start
working"). Team: Hemnaath (lead: Box + Agent), Mithuna (Watcher), Rahul (Story). Who does what,
and the contracts between us: `plans/SCOPE-OF-WORK-site-safety-watch.md`. Changes after the
lock go through the captain and are logged in `MEMORY.md`.

**One line:** an always-on safety officer that watches a site's cameras on one Dell Pro Max
with GB10, spots a blocked exit, and posts the event to Slack with a privacy-safe evidence
frame, a locally stored safety rule and a fix to approve. Raw video never leaves the box.

**Completion rule:** ship one reliable hazard end to end before adding a second hazard or any
extra integration. The minimum winning loop is clip to local vision to de-duplicated event to
Slack to human disposition to an auditable record.

---

## 1. Why this idea (and why now)

- The organizers want projects that show what the box can do, with a real use case, and with
  everything running on the box. This one keeps a vision model busy on live video all day,
  next to an agent that reasons and acts. That is the box's strength: 128 GB of unified memory
  and a model that reads images and video.
- Our main model already sees: `nvidia/Qwen3.6-35B-A3B-NVFP4` takes text, image and video input
  ([model card](https://huggingface.co/nvidia/Qwen3.6-35B-A3B-NVFP4)). It is on our SSD, so
  vision costs no download (the box downloads at about 2.7 MB/s, measured today).
- Visual projects win on this hardware: the NYC Spark Hack winner was "a 3D time machine for
  every building in NYC" ([post](https://x.com/i/status/2052810727967322329)).

## 2. Problem, buyer, value

**Problem.** Most hazards are visible on camera long before someone gets hurt: a pallet left in
an exit route, a spill nobody reported, a cable across a walkway. Sites already have cameras,
but nobody watches them for hazards; footage is reviewed after the injury.

**Evidence (checked today):**
- Serious workplace injuries cost US employers **$58.7B a year**; falls on the same level alone
  cost **$10.5B** ([Liberty Mutual Workplace Safety Index 2025](https://www.libertymutualgroup.com/about-lm/news/articles/us-companies-spend-50.87b-year-top-ten-causes-serious-workplace-injuries-according-2025-liberty-mutual-workplace-safety-index)).
- OSHA's maximum penalty is **$16,550 per serious violation** and **$165,514 per willful or
  repeated** one in 2026 (frozen at 2025 levels) ([OSHA 2026 penalty memo](https://www.osha.gov/memos/2026-05-21/2026-annual-adjustments-osha-civil-penalties),
  [summary](https://bayareacompliance.com/resources/osha-fines-2026)).
- Exit routes must be "free and unobstructed" with no materials placed in them, even
  temporarily ([29 CFR 1910.37](https://www.osha.gov/laws-regs/regulations/standardnumber/1910/1910.37)).
  Walking-working surfaces must be kept clean and orderly (29 CFR 1910.22).
- Companies already pay for camera-based safety: Voxel raised a $44M Series B
  ([PR Newswire](https://www.prnewswire.com/news-releases/voxel-raises-44m-in-series-b-funding-to-transform-workplace-safety-with-its-ai-powered-platform-302471555.html)),
  Protex AI a $36M Series B, and Intenseye covers 100,000+ workers
  ([Protex market report](https://www.protex.ai/the-safety-computer-vision-market-report-2026)).

**Buyer and owner.** EHS (environment, health and safety) manager of a warehouse, plant or
distribution center. Daily user: the shift supervisor who gets the Slack alert and fixes it.

**Value we can claim honestly.** Hazards caught and fixed before an injury, time from hazard to
fix, and an audit trail of every hazard with evidence. ROI figures on slides are labelled
assumptions unless we measured them.

**Why it must run locally (Local-first design, 25%).**
1. The raw video can show employees all day. Keeping it on site is the privacy promise to
   workers and their representatives. Only a privacy-safe evidence frame is posted to Slack.
2. Bandwidth and cost: sending every camera, all day, to a cloud vision model is expensive.
   (Assumption to label: a 1080p camera stream is a few Mbps; we can measure our own clip's
   bitrate with ffprobe.)
3. It keeps working when the internet does not; alerts queue and send when it comes back.

**How we differ from Voxel and Protex.** One box on site, no raw cloud video, and an agent that
does more than detect: it explains the rule, proposes the fix, waits for a human disposition
and creates an auditable local record. Q&A and daily reporting are roadmap extensions.

## 3. What the judges will see (the demo)

No live demo at the pitch: we submit a video, and the slides can embed it. Target 2 to 3
minutes of video (assumption: confirm the limit at the Help Desk).

Core story beats:
1. A warehouse corner (filmed at the venue today). Text on screen: "recorded today, replayed in
   real time; all inference on the GB10."
2. Someone parks a cart in front of the exit door and walks away.
3. Slack #safety shows a card: a frame staged without faces, "Exit route blocked",
   "29 CFR 1910.37: exit routes must be free and unobstructed", the fix ("move the cart, tag
   the zone"), and a clear Approve or False alarm action.
4. The supervisor approves it. The agent creates a local work-order record and replies with the
   event ID and status.
5. End on two measured numbers from the run: hazard-to-alert latency and results on the small
   labelled test set. State the test-set size on screen.

After the core video has been recorded, add at most one extra beat: a scheduled digest or a
camera-based resolution confirmation. Do not require both.

## 4. How it works on the GB10

```
cameras (our clips replayed as live streams)
   -> watcher (Python, on the box)
        fixed-rate frame sampler
        -> vision check: Qwen3.6 on vLLM (localhost:8000), frame + hazard checklist,
           returns JSON {hazard, zone, confidence, explanation}
        -> de-duplicate (same hazard in the same zone within N minutes is one event, not many)
        -> event store (SQLite) + evidence frame on disk
   -> OpenClaw agent in Slack
        core tools: list_new_events, get_event, lookup_rule, set_disposition
        core trigger: new event check
   -> Slack gets text + a privacy-safe evidence frame; raw clips remain local
```

Add a motion gate, second look, automatic resolution check and local viewer only after the
core loop has been recorded. A fixed-rate sampler is sufficient for the submitted demo.

Models (all local):
- Vision and agent: `nvidia/Qwen3.6-35B-A3B-NVFP4` on vLLM, port 8000. One model does both, so
  memory stays simple. Measure whether vision calls and agent turns slow each other down.

Stack rules from the event: use at least one of NemoClaw, OpenClaw or OpenShell. The core uses
OpenClaw because Slack is part of the judged workflow. **Decision at lock:** we get OpenClaw
through NVIDIA's NemoClaw installer (the supported Spark path), which runs it inside an
OpenShell sandbox wired to our local vLLM, so all three are used. If the sandbox blocks the
agent from reaching the watcher's CLI by 13:15, run OpenClaw directly on the host and keep
going. Runtime inference only on the box: no cloud model, not even as a fallback.

Measured on our box (11:34 to 11:36, see `MEMORY.md`): vLLM ready about 3 minutes after start;
one 960x640 image plus the question is 653 prompt tokens and about 1.0 s warm (1.6 s cold)
with thinking off. Images are sent as an OpenAI-style `image_url` data URI.

Known integration facts (from `~/claude-sessions/dell-nvidia-gb10/notes/openclaw-facts.md`):
- Slack approval buttons exist in OpenClaw's Slack channel. Replying without an @mention is a
  config key (`requireMention`), nesting to confirm on the box.
- Scheduled jobs: `openclaw cron --every 1m --command "<shell>"` runs without a model call;
  output of only `NO_REPLY` is suppressed. Use it for the new-event check.
- Slack image upload and interactive buttons are unconfirmed. The time-safe fallback is a text
  alert with an attached image and `approve <event_id>` or `false-alarm <event_id>` in Slack.

## 5. Scope

**Must ship (the demo path):**
1. Watcher on a replayed clip: fixed-rate sampling, one local vision check with structured JSON,
   de-duplication and SQLite event storage. Rule lookup is a plain table in code, not the model.
2. OpenClaw posts the event to #safety with the stored rule, proposed fix and evidence image.
3. A Slack reply or button marks the event approved or false alarm and writes the disposition
   to SQLite. A work order is the same row with an updated status, not another service.
4. Eval script on a small labelled set writes `numbers.json` (every number on slides comes
   from here).

**Hazard list.** Build and film blocked exit first. Add spill or trip hazard only after the
blocked-exit loop is recorded end to end. All other hazards are roadmap only:

| Hazard | Rule to cite (verify exact paragraph before the slide) |
|---|---|
| Exit route or exit door blocked | 29 CFR 1910.37 |
| Spill or wet floor with no sign | 29 CFR 1910.22 |
| Cable or object across a walkway (trip) | 29 CFR 1910.22 |
| Fire extinguisher blocked | 29 CFR 1910.157 |
| Standing on a chair or box to reach | unsafe practice (cite only if verified) |
| Missing PPE where required (hi-vis vest) | 29 CFR 1910.132 |

**Stretch (only after the demo path is recorded once):** second hazard, scheduled digest,
camera-based resolution confirmation, motion gate, second-look verification, face blur when
people appear, Slack buttons, Q&A, OpenShell refusal, offline queue, watts per camera, local
viewer, or a second camera. Pick at most two.

**Cut:** face recognition or naming people (never), real CCTV integration, multi-site
dashboards, model fine-tuning, a second model, and any external work-order integration.

## 6. Data we make today (rule: nothing made before doors opened)

- Film 6 to 8 clips of 10 to 20 seconds each with a phone, in our room and corridor. Keep
  strangers out of frame so face blur is not required for the core. About half contain the
  blocked-exit hazard and half are clean. State this small staged sample size beside every
  accuracy result.
- Name each file `NN_hazard_zone.mp4` and keep `labels.csv` (clip, hazard or none, second it
  starts). That is our ground truth for accuracy numbers.
- Replay clips as live streams with ffmpeg (`-re -stream_loop -1`), labelled on screen as replay.
- Everything is synthetic or staged by us; say so in the README and on the slides.

## 7. Roles (final; full detail in `plans/SCOPE-OF-WORK-site-safety-watch.md`)

| Person | Role | Owns | First deliverable |
|---|---|---|---|
| Hemnaath | Box + Agent (lead) | vLLM with vision (done), NemoClaw/OpenClaw + Slack, agent tools, alert and disposition, pitch | Slack alert from a fake event |
| Mithuna | Watcher | frame sampler, vision prompt, JSON validation, de-duplication, SQLite store, the `ssw` CLI, rule table | hazard event from one clip |
| Rahul | Story | filming, labels, replay, eval and numbers.json, demo video, slides, writeup, submission | 8 labelled clips by 13:00 |

Only Hemnaath connects to the box; teammates hand code, clips and scripts to him and get logs
and numbers back (see "Box access" in the scope of work).

Repo: `site-safety-watch`, created today on the box at `~/site-safety-watch`. GitHub remote
only when the captain says so; pushes only when the captain says "push".

Coding agents (Claude Code, Codex, Cursor) write code for each role; the product itself calls
only the box.

## 8. Timeline (today)

| Time | Goal | Gate (must be true to move on) |
|---|---|---|
| 11:43 | Locked. Models copied and verified; vLLM with vision up and measured | done |
| 11:45 to 12:45 | NemoClaw/OpenClaw + Slack, repo skeleton, first clips filmed | Gate 1: one frame in, hazard JSON out, from the box (passed 11:36); bot answers in Slack |
| 12:45 to 14:30 | Watcher on a clip, event store, first Slack alert and disposition | Gate 2: clip in, alert in Slack, disposition stored; record a backup video |
| 14:00 | Lunch at the desk | |
| 14:30 to 15:30 | Eval and reliability fixes on the core path | Gate 3: numbers.json from all labelled clips |
| 15:30 | Hard fallback deadline | if Slack buttons fail, use text commands; if image upload fails, post text plus local evidence ID |
| 15:30 to 16:15 | Record the complete core demo; add one stretch only if the recording succeeds | a complete recording exists |
| 16:15 to 17:00 | Fix demo blockers, README and writeup; no new architecture | |
| 17:00 | Feature freeze | |
| 17:00 to 17:35 | Final demo recording or edit from the 15:30 backup | |
| 17:35 to 18:00 | Submit on BuilderBase | submitted |
| 18:00 to 19:00 | Slides at a public link | submitted |
| 19:00 | Return the box. First: `sudo rm /etc/sudoers.d/90-hackathon` | |

## 9. Numbers to measure (none are known yet; do not put guesses on slides)

- Seconds from the hazard appearing in the clip to the Slack card.
- Correct hazard and clean classifications on the labelled clips, with the sample size shown.
- Optional only after those exist: frames checked per minute, tokens per event, unified memory
  in use and watts drawn by the box.

## 10. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Vision model misses or invents hazards | keep only blocked exit, tune on the staged clips, and show the small evaluation honestly |
| Too slow per frame | lower resolution and sample less often; the demo requires reliable event detection, not live frame rate |
| vLLM vision flags or memory | start with the model card's recipe; lower context and `--max-num-seqs` |
| OpenClaw cannot call the watcher directly | use SQLite or a local JSON event file as the handoff |
| Slack buttons fail | accept `approve <event_id>` and `false-alarm <event_id>` as text commands |
| Slack image upload fails | post the hazard, rule and local evidence ID; show the frame beside Slack in the demo video |
| Venue Wi-Fi drops | everything except Slack is local; queue alerts; the demo video is recorded from a good run |
| Crowded category (many CV safety demos) | lead with the complete loop: rule, proposed fix, human disposition and auditable record |

## 11. Judging rubric (25% each) and how we score

| Criterion | What earns it here |
|---|---|
| Technical execution | full loop on the box: camera to vision to agent tools to Slack to human disposition and stored record |
| Business value | named owner (EHS manager), $58.7B problem, cited OSHA penalties, existing paying market |
| Local-first design | all inference and raw video stay on the GB10; only the alert and privacy-safe evidence frame reach Slack |
| Demo quality | one clear story in the video, real Slack cards, measured numbers on screen |

## 12. Likely judge questions

- **Privacy of workers?** No face recognition. Raw video remains on the GB10. The core demo is
  staged without faces; production evidence frames would be blurred before posting.
- **False alarms?** Every event needs a human disposition, and we show results on the labelled
  staged test set with its sample size.
- **Why not Voxel?** Raw video stays on one local box, and the agent closes the loop from
  detection through human disposition and an auditable record.
- **Scale?** One box per site (assumption: cameras per box is a number we measure, not claim).

## 13. Rules everyone follows (from the event and the captain)

- Runtime inference only on the GB10. No cloud model or API in the product, not even fallback.
- Nothing from Canary Pact (code, prompts, data, UI).
- No AI attribution in commits, README, writeup or slides. No em dashes anywhere.
- Every number on slides comes from `numbers.json` or is labelled as an assumption.
- Shared log for Claude Code and Codex: `MEMORY.md` in the hackathon folder.

## 14. Committee compliance gate

Checked against the committee slide photographed at 11:30 on the event day:

| Committee requirement | Current alignment | Proof or required action |
|---|---|---|
| No pre-built agents; plans, scaffolds and libraries are allowed | Aligned | Product code is being created after doors opened. Preserve file timestamps and commit history. Do not reuse Canary Pact code, prompts, fixtures or UI. |
| Use at least one of NemoClaw, OpenClaw or OpenShell | Open blocker until demonstrated | OpenClaw is the selected required stack. Install it, route a real alert and human disposition through it, and capture that in the demo video. Running vLLM with a NemoClaw recipe alone is not proof of using NemoClaw. |
| All inference runs locally on the on-site GB10 | Aligned in architecture; verify end to end | Every runtime model URL must resolve to the GB10 local vLLM endpoint. No hosted model fallback. Capture the vLLM container and local endpoint in the evidence log. |
| No live demo; submission must include video; pitch uses submitted slides only | Aligned | Record the end-to-end demo before feature freeze. Make the slides self-contained because the team cannot use its own computer or the GB10 during the pitch. |
| Project deadline at 18:00; no more coding | Aligned | Internal feature freeze remains 17:00. Only recording, editing, writeup and submission work follows. Stop all code changes at 18:00. |
| Pitch deck deadline and computer return at 19:00 | Aligned | Submit the public slide link and remove `/etc/sudoers.d/90-hackathon` before returning the box. |
| Top 8 pitch at 19:30; five minutes per team | Aligned | Keep the submitted slide narration within five minutes and assume no live system access. |

**Required compliance evidence before submission:** one timestamped local-inference log, one
OpenClaw-triggered Slack event with disposition, repository history showing day-of product
work, the submitted demo video, and the submitted public slide link.

## 15. Changes after the lock (captain, 12:20 to 13:15)

The completion rule still holds: the blocked-exit loop (clip, local vision, event, Slack, human
decision, stored record) comes first. Everything below is either done or a stretch with a drop
deadline of 16:00.

1. **Stack in use:** NemoClaw sandbox `safety` running OpenClaw inside OpenShell, inference
   through `inference.local` to our vLLM. Gate 1 passed at 12:38 (bot answers in #safety).
   Box wiring: `agent/box/README.md`.
2. **Alerts are posted by code, not the model.** An OpenClaw cron command job runs
   `ssw.mjs post-new` every minute. Measured: the first version, a full agent turn per check,
   used 135,359 input + 3,963 output tokens and 63 s per run; the command job posts the same
   alert in 0.51 s with zero model tokens. The model is kept for reading frames, recording
   decisions and answering people.
3. **Accuracy on low-quality CCTV** (watcher switches, each measured on and off):
   `SSW_ENHANCE` (exit-zone crop, 2x upscale, CLAHE), `SSW_LOCATE` (Qwen3.6 returns the
   obstruction box; code checks overlap with the exit zone), `SSW_VOTE=3/4` (seen in 3 of the
   last 4 samples), `SSW_VERIFIER_URL` (NVIDIA **Cosmos-Reason2-2B** on port 8001 as a second
   opinion on the last 4 frames). Eval adds CCTV-angle, dim and degraded 360p copies of every
   clip. Cosmos is under the NVIDIA Open Model License (commercial use allowed); the console and
   README must say "Built on NVIDIA Cosmos". `nvidia/LocateAnything-3B` is not used
   (non-commercial).
4. **3D room view** (stretch, drop at 16:00 if not solid): `agent/scene3d/` runs
   Depth-Anything-V2-Small (Apache-2.0) on the GB10 GPU and returns a colored point cloud with
   the obstruction lit up; the console renders it with vendored three.js. Measured: 13.7 to
   17.2 ms of GPU depth per frame, 68,480 points, 48 to 68 ms per request. Depth is relative and
   from one camera; the 70 degree field of view is an assumption shown in the data.
5. **Frontend:** the console in `agent/viewer/` is built by Hemnaath with Codex (PR #8).
6. **Contract addition (agreed):** events get a nullable `box` = `[x1, y1, x2, y2]` in pixels of
   `frame_path`, written by the watcher, used by the console and the 3D view.
7. **Demo beats add:** the 3D room with the blocked exit lit up, and the line "three vision
   models on one GB10: Qwen3.6 reads the scene, Cosmos-Reason2 double-checks it, Depth Anything
   builds the 3D view".

Measured on our GB10 so far (all from logged runs today):

| What | Value |
|---|---|
| Qwen3.6, one 960x640 frame plus question | 1.03 s warm, 653 prompt + 69 output tokens |
| vLLM start to ready | about 3 min (weights 17.9 s) |
| Alert check as an agent turn vs as a command job | 63 s and 139,322 tokens vs 0.51 s and 0 tokens |
| Depth Anything V2 Small, fp16, cuDNN off | 13.6 ms per 518x784 frame |
| Models and images copied from SSD and verified | 91 GB in about 3 min |
