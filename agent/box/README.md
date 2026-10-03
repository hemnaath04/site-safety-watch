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
