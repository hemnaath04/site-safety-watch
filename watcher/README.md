# watcher (Mithuna)

Turns a clip into clean, de-duplicated blocked-exit events in `data/ssw.db`, and exposes
them through the `ssw` CLI (the seam with the agent). Core hazard: blocked_exit only.

## Install
```
pip install -r watcher/requirements.txt   # OpenCV, only needed to read real frames
```

## Run on a laptop (no box, no clips)
Drive the loop from the fake vision client to smoke-test the logic:
```
python -m watcher.watcher --fake-vision --no-frames --zone exit_a
```

## Run on a clip (laptop with OpenCV, still fake model)
```
python -m watcher.watcher --clip data/clips/01_blocked_exit.mp4 --zone exit_a --fake-vision
```

## Run for real (box only, Hemnaath)
Same command without `--fake-vision`. Reads `VLLM_BASE_URL` (default
`http://127.0.0.1:8000/v1`) and the model `nvidia/Qwen3.6-35B-A3B-NVFP4`.

## File mode (eval) vs stream mode (demo)
- **File mode** (Rahul's eval): point `--clip` at an mp4. The watcher reads to the end and
  stops. Use `--max-frames N` to bound a run.
- **Stream mode** (live demo): Rahul replays a clip as a stream, for example
  `ffmpeg -re -stream_loop -1 -i clip.mp4 -f mpegts udp://127.0.0.1:5000`. Run the watcher
  with `--stream` and the same URL as `--clip`; it reconnects if the stream drops and
  stops cleanly only when the stream is truly gone.
- Agree the exact replay URL with Rahul; the watcher takes whatever OpenCV can open (a
  file path, a udp/rtsp/http URL).

Zone is resolved from the clip name (`NN_hazard_zone.mp4`) or `watcher/zones.py`; pass
`--zone` to override.

## The ssw CLI (contract 0.5)
Each command prints JSON only. `ssw pending` prints the bare string `NO_REPLY` when empty.
```
./watcher/ssw events --status new
./watcher/ssw event <id>
./watcher/ssw rule blocked_exit
./watcher/ssw mark-posted <id>
./watcher/ssw dispose <id> approved|false_alarm --by <slack_user>
./watcher/ssw pending
```
Tip: `alias ssw="python -m watcher.ssw"` from the repo root.

## Settings (env)
`VLLM_BASE_URL`, `SSW_MODEL`, `SSW_DB`, `SSW_INTERVAL` (seconds, default 2),
`SSW_FRAME_WIDTH` (default 960), `SSW_MIN_CONFIDENCE` (default 0.6),
`SSW_DEDUP_MIN` (default 5).

## Contracts
Event JSON 0.1, SQLite 0.2, rule table 0.3, vision endpoint 0.4, `ssw` CLI 0.5, all in
`plans/SCOPE-OF-WORK-site-safety-watch.md`. Build against them exactly.

## Safety and efficiency features
- **Face blur (on by default).** The saved evidence frame has any detected face blurred
  before it can be posted. It is a no-op when no face is found. Turn it off only on clips
  that provably contain no people: `--no-blur`. If the face cascade cannot load, the run
  stops rather than risk posting a face.
- **Second look** (`--second-look`): confirm a candidate with a stricter re-ask before
  storing it, which cuts false alarms. Off by default so the core loop is unchanged.
- **Motion gate** (`--motion-gate`): skip the vision call when the scene has not changed,
  which keeps an always-on stream cheap. Off by default. Tune with `SSW_MOTION_THRESHOLD`.

Example for the live demo on the box:
```
python -m watcher.watcher --clip udp://127.0.0.1:5000 --stream --second-look --motion-gate
```

## Accuracy switches (post-lock, each off by default, measured on and off)
- **`--vote 3/4`** (or `SSW_VOTE=3/4`): only alert when the hazard is seen in 3 of the last
  4 samples. Cuts single-frame false alarms.
- **`--enhance`** (`SSW_ENHANCE=1`): crop to the exit zone, upscale 2x, CLAHE the frame sent
  to the model (the saved evidence frame stays the original). Needs an `exit_box` in
  `zones.json` for the crop, otherwise it enhances the whole frame.
- **`--locate`** (`SSW_LOCATE=1`): ask the model for the obstruction box and require it to
  overlap the exit zone (`SSW_LOCATE_MIN_OVERLAP`, default 0.1). The box is stored on the
  event (nullable `box` column).
- **`--verifier-url http://127.0.0.1:8001/v1`** (`SSW_VERIFIER_URL`): a second local model
  (NVIDIA Cosmos) confirms a candidate. Fails open on any error, so a flaky verifier never
  drops a real hazard.
- **`zones.json`**: per-zone config, `{"exit_a": {"exit_box": [x,y,w,h]}}`, used by enhance
  and locate. Override the path with `SSW_ZONES`.
- **`data/decisions.jsonl`**: one JSON line per processed frame (hazard, confidence, box,
  present, voted, action) for debugging and the eval. Override with `SSW_DECISIONS`.

Measured demo run on the box:
```
python -m watcher.watcher --clip <replay-url> --stream --vote 3/4 --enhance --locate \
    --second-look --verifier-url http://127.0.0.1:8001/v1
```

## Tests
```
python -m unittest discover -s watcher/tests
```
52 tests. The two that need OpenCV (blur, motion decode) skip where it is not installed and
run on the box.
