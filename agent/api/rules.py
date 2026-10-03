"""Rule table (scope section 0.3). Plain code, never the model."""

RULES = {
    "blocked_exit": {
        "cite": "29 CFR 1910.37",
        "text": "Exit routes must be free and unobstructed.",
        "fix": "Move the obstruction out of the exit route and tag the zone.",
    },
}

TITLES = {
    "blocked_exit": "Exit route blocked",
}


def get_rule(hazard: str) -> dict | None:
    rule = RULES.get(hazard)
    return dict(rule) if rule else None


def title_for(hazard: str) -> str:
    return TITLES.get(hazard, hazard.replace("_", " ").capitalize())
