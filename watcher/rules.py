"""Hazard enum, the rule table, the vision prompt, and Event JSON validation.

Contract 0.1 and 0.3. The rule citation and the fix are a plain table here, never written
by the model. The model only classifies the hazard and explains what it saw.
"""
from __future__ import annotations

# Core demo is blocked_exit only. spill and trip_cable join the enum after Gate 2.
HAZARDS = ["blocked_exit", "none"]

# hazard -> OSHA citation and the fix text (deterministic).
# Verify each exact paragraph on osha.gov before it goes on a slide.
RULE = {
    "blocked_exit": {
        "cite": "29 CFR 1910.37",
        "text": "exit routes must be kept free and unobstructed",
        "fix": "Move the obstruction out of the exit route and tag the zone.",
    },
    # spill: 29 CFR 1910.22 (add after Gate 2)
    # trip_cable: 29 CFR 1910.22 (add after Gate 2)
}


def lookup_rule(hazard: str) -> dict:
    """Return {cite, text, fix} for a hazard, or empty strings if unknown."""
    r = RULE.get(hazard)
    if not r:
        return {"cite": "", "text": "", "fix": ""}
    return dict(r)


# What we send to the vision model. Ask for strict JSON only, matching contract 0.1.
# zone is passed in by the watcher from the clip config, not chosen by the model.
VISION_PROMPT = (
    "You are a workplace safety inspector looking at one still frame from a site camera. "
    "Check only for this hazard: a blocked exit, meaning anything placed in or blocking an "
    "exit route or an exit door (a cart, boxes, a stack of chairs, equipment). "
    "If the exit route is clear, the hazard is none. "
    "Reply with ONLY this JSON and nothing else: "
    '{"hazard": "blocked_exit" or "none", '
    '"confidence": a number from 0.0 to 1.0, '
    '"explanation": "one sentence naming what is blocking the exit, or why it is clear"}'
)

# Stretch: a stricter re-ask to confirm a candidate and cut false alarms (after Gate 2).
SECOND_LOOK_PROMPT = (
    "Look again carefully. Is an exit route or exit door really blocked in this frame? "
    "Do not report a hazard unless you are confident. Reply with ONLY the same JSON format."
)


# LOCATE variant: also ask for the obstruction box so code can check it is in the exit zone.
LOCATE_PROMPT = (
    "You are a workplace safety inspector looking at one still frame from a site camera. "
    "Check only for this hazard: a blocked exit, meaning anything placed in or blocking an "
    "exit route or an exit door. If the exit route is clear, the hazard is none. "
    "Reply with ONLY this JSON and nothing else: "
    '{"hazard": "blocked_exit" or "none", '
    '"confidence": a number from 0.0 to 1.0, '
    '"explanation": "one sentence naming what is blocking the exit, or why it is clear", '
    '"box": [x, y, width, height] of the obstruction in pixels, or null if none}'
)


def _valid_box(box) -> bool:
    """A box is optional; if present it must be four non-negative numbers."""
    if box is None:
        return True
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return False
    try:
        return all(float(v) >= 0 for v in box)
    except (TypeError, ValueError):
        return False


def validate_event(obj) -> bool:
    """Guard against malformed model output before anything is stored."""
    if not isinstance(obj, dict):
        return False
    if obj.get("hazard") not in HAZARDS:
        return False
    try:
        c = float(obj.get("confidence", 0))
    except (TypeError, ValueError):
        return False
    if not 0.0 <= c <= 1.0:
        return False
    if not isinstance(obj.get("explanation", ""), str):
        return False
    if not _valid_box(obj.get("box")):
        return False
    return True
