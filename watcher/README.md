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

## Stretch (after Gate 2)
Second look on candidates, motion gate, face blur (required if any posted frame shows a face).
