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


# The raw schema the vision model must return, enforced by vLLM guided decoding at
# temperature 0 so the reply is always well formed (this is what fixes the second look,
# which used to get free text back and discard real sightings). vision.py maps this raw
# shape to the internal event (hazard, zone, confidence, explanation, box) below.
VISION_SCHEMA = {
    "type": "object",
    "properties": {
        "exit_visible": {"type": "boolean"},
        "blocked": {"type": "boolean"},
        "box": {
            "type": ["array", "null"],
            "items": {"type": "number"},
            "minItems": 4,
            "maxItems": 4,
        },
        "confidence": {"type": "number"},
        "explanation": {"type": "string"},
    },
    "required": ["exit_visible", "blocked", "confidence", "explanation"],
    "additionalProperties": False,
}

# What we send to the vision model. The enforced schema guarantees the fields; the prompt
# tells the model how to decide them. zone is set by the watcher, not the model.
VISION_PROMPT = (
    "You are a workplace safety inspector looking at one still frame from a site camera. "
    "Decide two things: is an exit route or exit door visible in the frame (exit_visible), "
    "and is it blocked by anything such as a cart, boxes, a stack of chairs or equipment "
    "(blocked). If an exit is blocked, give box as the bounding box of the obstruction, "
    "otherwise box is null. Give a confidence from 0.0 to 1.0 and a one sentence explanation."
    # Note: Qwen returns the box as 0..1000 xyxy regardless of wording; vision.py converts it
    # to pixel [x, y, w, h] of the frame.
)

# Stricter re-ask used by the second look. Same enforced schema, so the reply still parses.
SECOND_LOOK_PROMPT = (
    "Look again carefully at this frame. Set blocked to true only if an exit route or exit "
    "door is clearly obstructed; if you are unsure, set blocked to false. Report exit_visible, "
    "blocked, box, confidence and a one sentence explanation."
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
