# Demo video script (2 to 3 min)

Recorded with Hemnaath running the box. No em dashes, no AI credits anywhere. Keep it to one
clean story. If a live run wobbles, cut to the captured Gate 2 run (temperature 0, same result).

Target length 2:30. Times are cumulative.

---

## 0:00 to 0:12  Problem
- On screen: the camera view of the exit door, calm.
- Voice: "Every site already has cameras. Nobody is watching them live. The footage that could
  have stopped the injury only gets reviewed after it."
- On screen text: "$58.7B a year in serious injuries. OSHA up to $16,550 per violation."

## 0:12 to 0:22  Setup, and it is local
- On screen: the Dell Pro Max with GB10, a terminal showing the local model, network indicator.
- Voice: "This runs entirely on one box. No cloud. The video never leaves the building."
- On screen text: "Local on 1x GB10. Qwen3.6 vision, on the box."

## 0:22 to 1:05  The hazard and the alert
- On screen: someone places a cart in front of the exit, walks out of frame, leaves it.
- Cut to Slack: the alert card appears, hazard + zone + "29 CFR 1910.37: exit routes must be
  free and unobstructed" + the fix + a blurred evidence frame.
- Voice: "A cart is left in the exit route. Within a second the agent posts the hazard, the exact
  OSHA rule it breaks, and a fix. It never raises an alert it cannot prove: no frame and no rule,
  no alert."

## 1:05 to 1:30  Approve and auto-resolve
- On screen: supervisor types "approve <id>" in Slack. Agent replies with the work order id.
- Then: the cart is removed. The agent re-checks and posts "resolved, exit clear" with a frame.
- Voice: "The supervisor approves. A work order opens. When the cart is gone, the agent confirms
  on camera and closes it out. The whole incident, start to finish."

## 1:30 to 1:45  The 3D twin
- On screen: the console, the depth point-cloud of the room rotating, the obstruction lit in red.
- Voice: "It also builds a 3D view of the floor on the box and flags the blockage in space."

## 1:45 to 2:10  Numbers and robustness
- On screen: the numbers (1.0 s per check, 24 cameras on one box, alert in 0.5 s, accuracy with
  sample size). Then the same detection on a degraded 360p copy.
- Voice: "One second per camera check, around two dozen cameras on a single box, alerts in half a
  second. And it still catches the blocked exit on a cheap, degraded camera."

## 2:10 to 2:25  Local-first proof
- On screen: the agent is asked to send a clip outside; OpenShell refuses it on screen. A traffic
  pane shows nothing leaving.
- Voice: "It cannot leak the video, because the sandbox will not let it. Local first, by
  construction."

## 2:25 to 2:40  Close
- On screen: "Site Safety Watch. One box per site." team names. EXIT CLEAR badge.
- Voice: "Site Safety Watch. The safety officer that never blinks, and never lets the video leave
  the building."

---

### Shot checklist before recording
- [ ] Hero clip: clear, cart placed, person leaves frame, then removed (the block-then-clear take)
- [ ] Slack alert card with rule + fix + blurred frame
- [ ] approve <id> reply
- [ ] auto-resolved message with frame
- [ ] 3D console with obstruction in red
- [ ] numbers on screen (from numbers.json + measured figures)
- [ ] OpenShell refusal + a no-traffic pane
- [ ] backup: the captured Gate 2 run, in case a live step fails
