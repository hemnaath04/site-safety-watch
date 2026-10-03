# Site Safety Watch

An always-on safety agent that watches a site's cameras on a single Dell Pro Max with GB10,
catches a blocked fire exit, and posts it to the team with a privacy-safe evidence frame, the
exact OSHA rule, and a fix to approve. All inference runs on the box. Raw video never leaves it.

Built on Saturday 2026-10-03 at the Dell x NVIDIA AI Hackathon, Boston. Everything in the repo
was written after doors opened that day.

## The problem
Sites already have cameras, but nobody watches them live. A blocked fire exit, a spill, a cart in
a walkway: the footage that could have prevented the injury is only reviewed afterward. Serious
workplace injuries cost US employers about $58.7B a year (Liberty Mutual 2025), and OSHA penalties
reach $16,550 per serious violation and $165,514 per willful or repeated one.

## What it does
1. Samples each camera on the box and checks the frame with a local vision model.
2. On a real hazard, posts to the channel: hazard, zone, the cited rule (29 CFR 1910.37 for a
   blocked exit), a proposed fix, and a blurred evidence frame.
3. The supervisor approves or flags a false alarm in the channel; an approval opens a work order.
4. The agent re-checks the camera and closes the work order when the exit is clear.

It raises nothing it cannot prove: no evidence frame and no cited rule means no alert.

## How it runs (all local on one GB10)
- Vision: Qwen3.6 multimodal on vLLM.
- 3D scene: Depth Anything builds a point-cloud twin with the obstruction flagged.
- People: RT-DETR, so a person walking through is not a false alarm.
- Agent and sandbox: NemoClaw and OpenClaw running inside an OpenShell sandbox that blocks
  outbound network by default.

## Measured on the box today
- About 1.0 s per camera check (warm), 653 prompt and 69 output tokens.
- Around 24 cameras on one box, GPU near 94% busy (confirm).
- An alert posts in 0.5 s as a model-free command, versus a full agent turn (~63 s) if run as one.
- 91 GB of models copied and verified in about 3 minutes.
- Accuracy on our staged clips: caught, missed, and false alarms with the sample size stated
  (from numbers.json, filled from the box run). Robustness is measured across camera quality:
  phone, CCTV angle, dim, and a degraded 360p copy.

Every number is measured on the GB10 or is clearly labelled an assumption.

## Local-first and privacy
Raw video stays on the box. Only a privacy-safe, face-blurred evidence frame reaches the channel.
OpenShell blocks outbound traffic by default, so the video cannot leave even if the agent is told
to send it. This is the reason the product runs on-site rather than in the cloud.

## Buyer and value
The buyer is the EHS manager of a warehouse, plant, or distribution center; the daily user is the
shift supervisor. Value: hazards caught and cleared before an injury, a measured time-to-clear,
and an auditable record of every hazard with evidence. One box covers many cameras. Pricing is an
assumption at this stage.

## Roadmap
A full-site bird's-eye view with people and forklift movement tracking in 3D, the way autonomous
vehicles model a scene.

## Built with
Open-source components, declared: vLLM, Qwen3.6, Depth Anything, RT-DETR, NemoClaw, OpenClaw,
OpenShell, OpenCV, ffmpeg, Python. Staged test clips filmed by the team on the day.

## Team
Hemnaath, Mithuna, Rahul.
