"""Door state from per-camera vision answers. Pure code, no model."""

DOOR_SCHEMA = {
    "type": "object",
    "properties": {
        "door_visible": {"type": "boolean"},
        "door_open": {"type": "boolean"},
        "blocked": {"type": "boolean"},
        "obstruction": {
            "anyOf": [
                {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 1000},
                 "minItems": 4, "maxItems": 4},
                {"type": "null"},
            ]
        },
    },
    "required": ["door_visible", "door_open", "blocked", "obstruction"],
    "additionalProperties": False,
}


def validate_report(obj):
    """Return a clean report dict or None if the model's JSON does not fit the schema."""
    if not isinstance(obj, dict):
        return None
    out = {}
    for key in ("door_visible", "door_open", "blocked"):
        if not isinstance(obj.get(key), bool):
            return None
        out[key] = obj[key]
    box = obj.get("obstruction")
    if box is not None:
        if (not isinstance(box, list) or len(box) != 4
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box)):
            return None
        box = [max(0, min(1000, int(round(v)))) for v in box]
        if box[2] <= box[0] or box[3] <= box[1]:
            box = None
    out["obstruction"] = box
    return out


def merge_door(reports):
    """Merge one door's reports from every camera that answered.

    Only cameras that see the door count. Blocked if any of them says blocked. Open if a strict
    majority says open. Returns None when no camera sees the door (keep the previous state).
    obstruction_floor comes from the first blocked report that has one.
    """
    seen = [r for r in reports if r and r.get("door_visible")]
    if not seen:
        return None
    blocked = any(r.get("blocked") for r in seen)
    open_votes = sum(1 for r in seen if r.get("door_open"))
    floor = None
    if blocked:
        for r in seen:
            if r.get("blocked") and r.get("obstruction_floor"):
                floor = r["obstruction_floor"]
                break
    return {
        "open": open_votes * 2 > len(seen),
        "blocked": blocked,
        "obstruction_floor": floor,
        "cams_seeing": sorted(r.get("cam") for r in seen if r.get("cam")),
    }
