#!/usr/bin/env bash
# Start the 3D scene service on the box in its own container (name: scene3d).
# Reuses the vLLM image for torch and transformers. Never touches vllm-main.
# Usage: agent/scene3d/run.sh [repo_dir]   (repo_dir defaults to ~/site-safety-watch)
# Optional env: SSW_DEMO_CLIP (path inside the repo, e.g. data/clips/01_blocked_exit.mp4),
# SSW_API_URL, SCENE_PORT, SCENE_HFOV_DEG.
set -euo pipefail

REPO="$(cd "${1:-$HOME/site-safety-watch}" && pwd)"
MODELS="$HOME/gb10-transfer/models"
NAME=scene3d

if [ ! -d "$MODELS/Depth-Anything-V2-Small-hf" ]; then
  echo "missing $MODELS/Depth-Anything-V2-Small-hf" >&2
  exit 1
fi

CLIP_ARGS=()
if [ -n "${SSW_DEMO_CLIP:-}" ]; then
  CLIP_ARGS=(-e "SSW_DEMO_CLIP=/repo/${SSW_DEMO_CLIP#/}")
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  docker rm -f "$NAME" >/dev/null
fi

docker run -d --name "$NAME" --gpus all --network host \
  -v "$REPO":/repo \
  -v "$MODELS":/models:ro \
  -e SCENE_HOST=127.0.0.1 \
  -e SCENE_PORT="${SCENE_PORT:-8300}" \
  -e SCENE_HFOV_DEG="${SCENE_HFOV_DEG:-70}" \
  -e SSW_API_URL="${SSW_API_URL:-http://172.18.0.1:8100}" \
  -e SSW_REPO_ROOT=/repo \
  -e HF_HUB_OFFLINE=1 \
  -e TRANSFORMERS_OFFLINE=1 \
  "${CLIP_ARGS[@]+"${CLIP_ARGS[@]}"}" \
  --entrypoint python3 \
  gb10/vllm-spark:local \
  /repo/agent/scene3d/server.py

echo "started $NAME; check: curl -s http://127.0.0.1:${SCENE_PORT:-8300}/health"
echo "logs: docker logs -f $NAME"
