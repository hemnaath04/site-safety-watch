#!/usr/bin/env bash
# Start the local model server on the GB10 (run on the box only).
# Qwen3.6-35B-A3B NVFP4 with vision, using the flags of NemoClaw's DGX Spark recipe
# (managed-inference/recipes/vllm.qwen3-6-35b-a3b-nvfp4.spark-single.v1.yaml).
# It listens only on the box itself and on the Docker bridge, never on the venue Wi-Fi.
set -euo pipefail

MODELS="${MODELS:-$HOME/gb10-transfer/models}"
IMAGE="${IMAGE:-gb10/vllm-spark:local}"

docker rm -f vllm-main >/dev/null 2>&1 || true
docker run -d --name vllm-main --restart unless-stopped --gpus all --ipc host \
  --ulimit memlock=-1 --ulimit stack=67108864 \
  -p 127.0.0.1:8000:8000 -p 172.17.0.1:8000:8000 \
  -v "$MODELS":/models:ro \
  "$IMAGE" \
  vllm serve /models/Qwen3.6-35B-A3B-NVFP4 --served-model-name nvidia/Qwen3.6-35B-A3B-NVFP4 \
  --host 0.0.0.0 --port 8000 \
  --max-model-len 262144 --gpu-memory-utilization 0.4 --dtype auto --quantization modelopt \
  --kv-cache-dtype fp8 --attention-backend flashinfer --moe-backend marlin \
  --max-num-seqs 4 --max-num-batched-tokens 8192 --enable-chunked-prefill --async-scheduling \
  --enable-prefix-caching --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 --load-format fastsafetensors

echo "Started. Ready when this lists the model:"
echo "  curl -s http://127.0.0.1:8000/v1/models"
