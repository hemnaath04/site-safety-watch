#!/usr/bin/env bash
# Replay a recorded clip as a realtime, looping stream for the watcher, labelled REPLAY.
# Run on the box (Hemnaath). The watcher reads the same URL with --clip.
# Agree the stream URL with Mithuna. Default is a local UDP MPEG-TS stream.
#
# Usage: story/replay.sh data/clips/01_blocked_exit_exit_a.mp4 [udp://127.0.0.1:5000]
#
# Note: drawtext needs a font file on some systems. If ffmpeg complains, set FONT to a real
# path, or drop the overlay and add the REPLAY label in the video editor instead.
set -euo pipefail

CLIP="${1:?pass the clip path, e.g. data/clips/01_blocked_exit_exit_a.mp4}"
URL="${2:-udp://127.0.0.1:5000}"
FONT="${FONT:-/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf}"
OVERLAY="drawtext=fontfile=${FONT}:text='REPLAY recorded today':x=24:y=24:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.5"

echo "replaying ${CLIP} to ${URL} at realtime, looping; Ctrl C to stop"
ffmpeg -hide_banner -re -stream_loop -1 -i "${CLIP}" \
  -vf "${OVERLAY}" \
  -c:v libx264 -preset ultrafast -tune zerolatency -f mpegts "${URL}"
