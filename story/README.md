# story (Rahul)

Data, honest numbers, and everything the judges see. Every number on a slide comes from
`numbers.json` or is labelled an assumption. Always show the sample size next to a rate.
No em dashes, no AI credits anywhere.

## Files

- `labels.csv`: the ground truth, one row per clip.
- `validate_labels.py`: checks `labels.csv` before the eval runs.
- `eval.py`: runs the watcher over every clip, for each setting and quality, writes `numbers.json`.
- `degrade.py`: makes bad-footage (cctv360) copies to prove it works on cheap cameras.
- `measure_latency.py`: measures detection latency on the box during a realtime replay.
- `replay.sh`: replays a clip as a realtime looping stream, labelled REPLAY (box only).
- `tests/test_eval.py`: self-contained tests, no OpenCV or box needed.

## Depends on the watcher (and two team items)

The eval runs Mithuna's watcher (`python -m watcher.watcher`). To run before it is merged, pull
her branch into your local working tree only (do not commit it on this branch):
```
git fetch origin
git checkout origin/mithuna/ssw-watcher -- watcher/
git restore --staged watcher/
```
Two things the eval drives that the watcher side must support for the full numbers:
- Setting switches: `SSW_ENHANCE`, `SSW_LOCATE`, `SSW_VOTE`, `SSW_VERIFIER_URL`. Until honored,
  every setting returns the same numbers (the eval still runs and groups them).
- `data/decisions.jsonl` for latency: one JSON object per line with at least
  `{"clip","frame_sec","hazard"}` and optionally `"setting"`. Without it, counts still work and
  latency is null.

## labels.csv format

```
clip,hazard,start_sec,quality
01_blocked_exitA.mp4,blocked_exit,4,cctv_angle
02_clear_exitA.mp4,none,,cctv_angle
```
- `clip`: the file name in `data/clips/` (clips are never committed).
- `hazard`: `blocked_exit` or `none`.
- `start_sec`: the second the object is left alone (blank for a clear clip).
- `quality`: `phone`, `cctv_angle`, `dim`, or `degraded360`.

## Filming checklist (leader's plan)

- 10 to 20 s clips of the same exit door. Phone mounted high in a corner, wide, looking down
  like a real CCTV camera. Landscape. Do not move it between clips.
- Blocked (5 or more): someone parks a cart, boxes or a chair stack in front of the exit, walks
  out of frame, leaves it.
- Clear (5 or more): same door, nothing in front, and some where a person walks through the
  doorway without leaving anything (the false alarm we must not raise).
- 2 or 3 clips dim or from further away. No strangers' faces.
- Names: `NN_blocked_exitA.mp4` and `NN_clear_exitA.mp4`.
- AirDrop to Hemnaath as soon as you have 4, then the rest. Send `labels.csv` with them.

## Run it

```
# validate the answer key
python -m story.validate_labels --labels story/labels.csv

# bad-footage copies (box uses ffmpeg; a laptop falls back to OpenCV)
python -m story.degrade --clips-dir data/clips --labels story/labels.csv --append

# laptop harness check (fake vision; clear clips read as false alarms by design)
python -m story.eval --fake-vision --settings baseline,vote --out numbers.fake.json

# box, real numbers across all settings (Hemnaath)
python -m story.eval --settings all-settings --labels story/labels.csv --clips-dir data/clips --out story/numbers.json

# detection latency on the box during a realtime replay
python -m story.measure_latency --db data/ssw.db --zone exitA --hazard-start-sec 4
bash story/replay.sh data/clips/01_blocked_exitA.mp4
```

## What numbers.json contains

Per setting (baseline, enhance, locate, vote, all, all+cosmos) an `overall` block and a
`by_quality` block, each with: sample_size, caught, missed, false_alarms (on clear clips),
true_clean, recall, precision, median_latency_sec.

## Measured on the GB10 today (use these on slides, they are real)

- One camera frame read by Qwen3.6: 1.03 s warm (653 prompt + 69 output tokens).
- Alert as a full agent turn: 63 s and 135,359 input tokens per check. Same alert as a
  model-free command: 0.51 s and zero model tokens. (This is why the new-event check is a
  command, not a model turn.)
- 91 GB of models copied and verified on the box in about 3 minutes.

## Demo video beats

Camera view, cart left at the exit, Slack alert with the OSHA rule, supervisor types
`approve <id>`, the console with the 3D room and the obstruction lit up, then the numbers.
If the Cosmos verifier ships, slides and README must say "Built on NVIDIA Cosmos" (license term).

## Tests

```
python story/tests/test_eval.py
```
