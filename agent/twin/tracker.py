"""Fuse people seen by several cameras on the floor plan and track them with stable ids.

Standard library only. Positions are meters, times are seconds (monotonic).
"""

import math

FUSE_RADIUS_M = 0.6
MAX_SPEED_MPS = 3.0
GATE_SLACK_M = 0.5
EXPIRE_S = 1.5
VEL_ALPHA = 0.5


def fuse(detections, radius=FUSE_RADIUS_M):
    """detections: list of (x, y, cam_id). Returns [{"x", "y", "cams"}].

    Detections within radius of a cluster's mean merge, and the cluster keeps the mean. Two
    detections from the same camera never merge: one camera seeing two boxes means two people.
    """
    clusters = []
    for x, y, cam in detections:
        if not (math.isfinite(x) and math.isfinite(y)):
            continue
        best, best_d = None, radius
        for c in clusters:
            if cam in c["cams"]:
                continue
            d = math.hypot(x - c["x"], y - c["y"])
            if d <= best_d:
                best, best_d = c, d
        if best is None:
            clusters.append({"x": x, "y": y, "cams": [cam], "_n": 1})
        else:
            n = best["_n"]
            best["x"] = (best["x"] * n + x) / (n + 1)
            best["y"] = (best["y"] * n + y) / (n + 1)
            best["cams"].append(cam)
            best["_n"] = n + 1
    return [{"x": c["x"], "y": c["y"], "cams": sorted(c["cams"])} for c in clusters]


class Track:
    __slots__ = ("id", "x", "y", "vx", "vy", "cams", "last_seen")

    def __init__(self, id_, x, y, cams, t):
        self.id, self.x, self.y = id_, x, y
        self.vx = self.vy = 0.0
        self.cams = cams
        self.last_seen = t

    def as_dict(self):
        return {"id": self.id, "x": round(self.x, 3), "y": round(self.y, 3),
                "vx": round(self.vx, 3), "vy": round(self.vy, 3), "cams": list(self.cams)}


class Tracker:
    def __init__(self, max_speed=MAX_SPEED_MPS, expire_s=EXPIRE_S, slack_m=GATE_SLACK_M,
                 alpha=VEL_ALPHA):
        self.max_speed = max_speed
        self.expire_s = expire_s
        self.slack_m = slack_m
        self.alpha = alpha
        self.tracks: list[Track] = []
        self.next_id = 1

    def update(self, people, t):
        """people: output of fuse(). t: seconds. Returns the live tracks as dicts."""
        self.tracks = [tr for tr in self.tracks if t - tr.last_seen <= self.expire_s]
        pairs = []
        for ti, tr in enumerate(self.tracks):
            dt = max(0.0, t - tr.last_seen)
            gate = self.max_speed * dt + self.slack_m
            px, py = tr.x + tr.vx * dt, tr.y + tr.vy * dt
            for pi, p in enumerate(people):
                if math.hypot(p["x"] - tr.x, p["y"] - tr.y) > gate:
                    continue
                pairs.append((math.hypot(p["x"] - px, p["y"] - py), ti, pi))
        pairs.sort()
        used_t, used_p = set(), set()
        for _, ti, pi in pairs:
            if ti in used_t or pi in used_p:
                continue
            used_t.add(ti)
            used_p.add(pi)
            tr, p = self.tracks[ti], people[pi]
            dt = t - tr.last_seen
            if dt > 1e-6:
                ivx, ivy = (p["x"] - tr.x) / dt, (p["y"] - tr.y) / dt
                tr.vx = self.alpha * ivx + (1 - self.alpha) * tr.vx
                tr.vy = self.alpha * ivy + (1 - self.alpha) * tr.vy
            tr.x, tr.y, tr.cams, tr.last_seen = p["x"], p["y"], p["cams"], t
        for pi, p in enumerate(people):
            if pi not in used_p:
                self.tracks.append(Track(self.next_id, p["x"], p["y"], p["cams"], t))
                self.next_id += 1
        return [tr.as_dict() for tr in self.tracks]

    def snapshot(self, t):
        return [tr.as_dict() for tr in self.tracks if t - tr.last_seen <= self.expire_s]
