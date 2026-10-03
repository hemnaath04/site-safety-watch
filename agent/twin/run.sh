#!/usr/bin/env bash
# Start the live twin service on the box in its own container (name: twin).
# Reuses the vLLM image for torch, transformers and OpenCV. Never touches other containers.
# Usage: TWIN_CONFIG=agent/twin/cameras.json agent/twin/run.sh [repo_dir]
#   TWIN_CONFIG is a path inside the repo (default agent/twin/cameras.json).
#   repo_dir defaults to ~/site-safety-watch.
# Optional env: TWIN_PORT, TWIN_DETECT_MS, TWIN_DOOR_S, TWIN_SCORE, VLLM_BASE_URL, SSW_MODEL.
set -euo pipefail

REPO="$(cd "${1:-$HOME/site-safety-watch}" && pwd)"
MODELS="$HOME/gb10-transfer/models"
NAME=twin
CONFIG="${TWIN_CONFIG:-agent/twin/cameras.json}"
CONFIG="${CONFIG#/repo/}"

if [ ! -f "$REPO/$CONFIG" ]; then
  echo "missing config $REPO/$CONFIG (copy agent/twin/cameras.example.json and edit it)" >&2
  exit 1
fi
if [ ! -d "$MODELS/rtdetr_v2_r18vd" ]; then
  echo "missing $MODELS/rtdetr_v2_r18vd" >&2
  exit 1
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker rm -f "$NAME" >/dev/null
fi

docker run -d --name "$NAME" --gpus all --network host \
  -v "$REPO":/repo \
  -v "$MODELS":/models:ro \
  -e SSW_REPO_ROOT=/repo \
  -e TWIN_CONFIG="/repo/$CONFIG" \
  -e TWIN_HOST=127.0.0.1 \
  -e TWIN_PORT="${TWIN_PORT:-8400}" \
  -e TWIN_DETECT_MS="${TWIN_DETECT_MS:-100}" \
  -e TWIN_DOOR_S="${TWIN_DOOR_S:-3}" \
  -e TWIN_SCORE="${TWIN_SCORE:-0.5}" \
  -e TWIN_DET_MODEL=/models/rtdetr_v2_r18vd \
  -e VLLM_BASE_URL="${VLLM_BASE_URL:-http://127.0.0.1:8000/v1}" \
  -e SSW_MODEL="${SSW_MODEL:-nvidia/Qwen3.6-35B-A3B-NVFP4}" \
  -e HF_HUB_OFFLINE=1 \
  -e TRANSFORMERS_OFFLINE=1 \
  --entrypoint python3 \
  gb10/vllm-spark:local \
  /repo/agent/twin/server.py

echo "started $NAME; check: curl -s http://127.0.0.1:${TWIN_PORT:-8400}/twin/health"
echo "stats: curl -s http://127.0.0.1:${TWIN_PORT:-8400}/twin/stats"
echo "calibrate: http://127.0.0.1:${TWIN_PORT:-8400}/twin/calibrate/<cam>"
echo "logs: docker logs -f $NAME"
