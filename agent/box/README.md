# The box: how the GB10 is set up

Only Hemnaath runs anything here (see AGENTS.md section 6).

## Model server

`start-vllm.sh` runs Qwen3.6-35B-A3B NVFP4 (text, image and video input) in the `vllm-main`
container on port 8000, with the flags of NemoClaw's DGX Spark recipe. It listens on
`127.0.0.1` and the Docker bridge `172.17.0.1` only, so nobody else on the venue Wi-Fi can use it.

Check it:

```bash
curl -s http://127.0.0.1:8000/v1/models
python3 agent/box/vision_smoke.py
```

## Measured on our box (Sat 2026-10-03)

| What | Value | How we measured |
|---|---|---|
| Copy of models and images from the SSD | 91 GB, all 112 checksums OK | `box-copy.sh` log, rsync then `sha256sum -c` |
| vLLM image load | 5 min | `time docker load -i images/vllm-spark.tar` |
| Weights load | 17.9 s (20.4 GiB) | `docker logs vllm-main` |
| Start to ready | about 3 min | container start 11:31:36, `/v1/models` answered 11:34 |
| KV cache | 23.1 GiB, 2,295,745 tokens | `docker logs vllm-main` |
| One image (960x640) plus question | 1.62 s first run, 1.04 s warm | `vision_smoke.py`, thinking off |
| Tokens for that call | 653 prompt, 69 completion | `vision_smoke.py` usage field |

The smoke test is a drawn scene, not a real photo. It shows image input works; it says nothing
about accuracy on real clips. Accuracy numbers come only from `story/numbers.json`.

vLLM reports that this GPU runs the FP4 weights through its Marlin weight-only path, so we do
not claim native FP4 speedups.

## How the agent is wired on the box

| Piece | Where | Notes |
|---|---|---|
| Sandbox | NemoClaw sandbox `safety` (OpenClaw 2026.7.1, OpenShell 0.0.116) | inference via `inference.local` to our vLLM |
| Model path for the sandbox | `host.openshell.internal:8000` = `172.18.0.1:8000` | forwarder `~/fwd/vllm-bridge-fwd.py` in tmux `vllm-fwd` to `127.0.0.1:8000` |
| Event API | tmux `ssw-api`: `agent/api/server.py` on `172.18.0.1:8100` | bridge only, not the venue Wi-Fi; `SSW_CMD` points at the `ssw` CLI |
| Sandbox network rule | `agent/policy/ssw-api.yaml` | only `node` may reach port 8100, five routes |
| Skill | `/sandbox/.openclaw/workspace/skills/site-safety-watch` | `nemoclaw safety skill install agent/skill/site-safety-watch` |
| #safety | `requireMention: false` for its channel id | so `approve <id>` works without an @mention |
| Alerts | OpenClaw cron command job, every 1 min: `node .../ssw.mjs post-new` | no model call; prints `NO_REPLY` when nothing is new |

Why alerts are a command job, not an agent turn: our first scheduled agent turn (same check,
light context, thinking off) used 135,359 input and 3,963 output tokens and took 63 s, longer
than the one minute interval (`openclaw cron runs`, 12:46). The alert text is fixed code output
anyway, so code posts it and the model is kept for reading frames and talking to people.

## How many cameras one GB10 handles (measured 13:53 to 14:05)

`loadtest.py` simulates cameras, each sending one frame every 2 s to Qwen3.6 with the exit
schema (thinking off), ramping the camera count, and samples `nvidia-smi` once a second.
0 errors at every level.

| Cameras | Checks per camera per min (target 30) | p50 / p95 latency | GPU busy | Power |
|---|---|---|---|---|
| 1 | 30.0 | 0.57 / 0.60 s | single samples | 22 W |
| 4 | 30.0 | 0.67 / 0.80 s | 92.7% | 48 W |
| 8 | 25.0 | 2.51 / 2.70 s | 94.0% | 56 W |
| 16 | 14.0 | 4.89 / 5.06 s | 93.3% | 56 W |
| 24 | 10.2 | 7.02 / 7.52 s | 92.9% | 56 W mean, 64 W max |

The ceiling is about 4.1 checks per second (compute-bound: 640 px frames and 16 concurrent
sequences did not raise it). A blocked exit is a static hazard, so one check every 6 s per
camera is enough: about 24 cameras per box.

## No telemetry from the inference containers

vLLM reports usage stats to stats.vllm.ai by default (hardware and config, no prompts). Found on
the box at 17:22 as open HTTPS connections from `vllm-main` and the unused `cosmos` container.
`start-vllm.sh` now sets `VLLM_NO_USAGE_STATS=1` and `DO_NOT_TRACK=1`. For the running containers,
the box blocks the default Docker bridge from the internet (the model files are local):

```bash
sudo iptables -I DOCKER-USER -i docker0 ! -d 172.16.0.0/12 -j REJECT    # undo: -D instead of -I
```

After the rule: 0 public connections from either container, vLLM still answers locally. The only
internet connection left on the box is the agent's Slack socket (wss-primary.slack.com).
