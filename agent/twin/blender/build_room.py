# Build a clean, complete 3D model of the monitored hall, headless on the GB10:
#   blender -b -P build_room.py -- <scan.glb> <scan-measure.json> <room-spec.json> <twin-config.json> <screen.jpg> <out.glb> <out-layout.json>
# Layout (walls, raked floor, curved desk rows, exits) is measured from the one-time LiDAR scan.
# Inventory and colors come from room-spec.json, written by the local VLM from the camera frames.
# The projector screen texture is cropped from the camera footage.
import bmesh, bpy, json, math, sys
import numpy as np
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
SCAN, MEASURE, SPEC, CFG, SCREEN, OUT, LAYOUT = a[:7]
meas, spec, cfg = json.load(open(MEASURE)), json.load(open(SPEC)), json.load(open(CFG))
CEIL_Z = 0.0
fz = lambda x, y: -0.0437 * x - 0.0099 * y - 2.517          # raked floor fit from the scan
C = np.array([-0.29, 0.48]); F = np.array([0.956, 0.292]); R = np.array([0.292, -0.956])
def rf2xy(r, f): p = C + r * R + f * F; return float(p[0]), float(p[1])

# ---- refit the four walls to the scan's vertical surfaces --------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SCAN)
o = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); bm.normal_update()
P = np.array([f.calc_center_median()[:] for f in bm.faces]); N = np.array([f.normal[:] for f in bm.faces])
bm.free()
hgt = P[:, 2] - fz(P[:, 0], P[:, 1])
vert = (np.abs(N[:, 2]) < 0.2) & (hgt > 1.0) & (hgt < 2.2)
VP = P[vert, :2]
walls = [np.array(p, float) for p in cfg["room"]["walls"]]
n = len(walls)
area = sum(walls[i][0] * walls[(i + 1) % n][1] - walls[(i + 1) % n][0] * walls[i][1] for i in range(n))
lines = []
for i in range(n):
    p0, p1 = walls[i], walls[(i + 1) % n]
    u = (p1 - p0) / np.linalg.norm(p1 - p0)
    nin = np.array([-u[1], u[0]]) if area > 0 else np.array([u[1], -u[0]])   # inward normal
    L = np.linalg.norm(p1 - p0)
    s = (VP - p0) @ u; d = (VP - p0) @ nin
    sel = (s > 0.1 * L) & (s < 0.9 * L) & (d > -1.5) & (d < 0.8)
    hist, e = np.histogram(d[sel], bins=np.arange(-1.5, 0.8, 0.05))
    shift = float(e[hist.argmax()] + 0.025) if sel.sum() > 50 else 0.0
    lines.append((p0 + shift * nin, u, nin))
    print(f"wall {i}: shift {shift:+.2f} m from {sel.sum()} points")
def meet(l1, l2):
    (p, u, _), (q, v, _) = l1, l2
    t = np.linalg.solve(np.array([u, -v]).T, q - p)
    return p + t[0] * u
corners = [meet(lines[i - 1], lines[i]) for i in range(n)]
wl = [(corners[i], corners[(i + 1) % n]) for i in range(n)]
print("corners", [[round(float(c[0]), 2), round(float(c[1]), 2)] for c in corners])

def inside(x, y, margin=0.0):
    for (p0, p1), (_, u, nin) in zip(wl, lines):
        if (np.array([x, y]) - p0) @ nin < margin: return False
    return True

# Exits snapped onto the refit walls (door centers from the config).
doors = []
for dcfg in cfg["room"]["doors"]:
    c = (np.array(dcfg["p1"]) + np.array(dcfg["p2"])) / 2
    best = None
    for i, ((p0, p1), (_, u, nin)) in enumerate(zip(wl, lines)):
        s = float((c - p0) @ u); dist = abs(float((c - p0) @ nin))
        if 0 < s < np.linalg.norm(p1 - p0) and (best is None or dist < best[0]): best = (dist, i, s)
    doors.append({"id": dcfg["id"], "wall": best[1], "s": best[2], "zone": dcfg.get("zone", dcfg["id"])})
print("doors", [(d["id"], d["wall"], round(d["s"], 2)) for d in doors])

# ---- materials ----------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
def lin(c): c = c / 255.0; return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
def mat(name, rgb, rough=0.85, metal=0.0, emit=0.0, cull=True, img=None):
    m = bpy.data.materials.new(name); m.use_nodes = True; m.use_backface_culling = cull
    b = m.node_tree.nodes["Principled BSDF"]
    col = (lin(rgb[0]), lin(rgb[1]), lin(rgb[2]), 1)
    b.inputs["Base Color"].default_value = col
    b.inputs["Roughness"].default_value = rough; b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = col; b.inputs["Emission Strength"].default_value = emit
    if img:
        t = m.node_tree.nodes.new("ShaderNodeTexImage"); t.image = bpy.data.images.load(img)
        m.node_tree.links.new(t.outputs["Color"], b.inputs["Base Color"])
        m.node_tree.links.new(t.outputs["Color"], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = 1.0
    return m
sp = lambda k, d: spec.get(k, d) if isinstance(spec.get(k), list) and len(spec.get(k)) == 3 else d
M = {
    "wall": mat("wall", sp("wall_rgb", [240, 240, 245]), 0.95, emit=0.35),
    "floor": mat("carpet", sp("floor_rgb", [60, 60, 70]), 1.0),
    "ceiling": mat("ceiling", sp("ceiling_rgb", [245, 245, 250]), 1.0, emit=0.8),
    "light": mat("light", [255, 252, 240], 0.5, emit=1.5),
    "desk": mat("desk", sp("desk_rgb", [210, 180, 140]), 0.6, cull=False),
    "panel": mat("desk_panel", [int(v * 0.85) for v in sp("desk_rgb", [210, 180, 140])], 0.7, cull=False),
    "chair": mat("chair", sp("chair_rgb", [50, 50, 55]), 0.7),
    "steel": mat("steel", [150, 152, 158], 0.35, metal=0.8),
    "door": mat("door", [int(v * 0.9) for v in sp("door_rgb", [230, 230, 235])], 0.6),
    "frame": mat("frame", [120, 122, 128], 0.5, metal=0.4),
    "glass": mat("glass", [200, 222, 240], 0.1, emit=0.9),
    "mullion": mat("mullion", [70, 72, 78], 0.5, metal=0.5),
    "exit": mat("exit_sign", [40, 200, 90], 0.4, emit=2.0),
    "screen": mat("screen", [255, 255, 255], 0.5, img=SCREEN),
    "black": mat("screen_frame", [20, 20, 22], 0.6),
    "board": mat("whiteboard", [250, 250, 252], 0.2),
    "rail": mat("handrail", [190, 150, 100], 0.5),
    "cap": mat("wall_top", [90, 94, 102], 0.8),
    "lectern": mat("lectern", [45, 45, 50], 0.6),
}
B = {k: bmesh.new() for k in M}

def face(bmx, pts, want, uv=None):
    f = bmx.faces.new([bmx.verts.new(p) for p in pts])
    f.normal_update()
    if f.normal.dot(Vector(want)) < 0: f.normal_flip()
    if uv is not None:
        lay = bmx.loops.layers.uv.verify()
        for loop in f.loops: loop[lay].uv = uv(loop.vert.co)
    return f
def box(bmx, c, s, yaw=0.0):
    m = Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, "Z") @ Matrix.Diagonal((s[0], s[1], s[2], 1.0))
    bmesh.ops.create_cube(bmx, size=1.0, matrix=m)

# ---- floor, ceiling, wall tops -------------------------------------------------------------
cz = [fz(*c) for c in corners]
face(B["floor"], [(c[0], c[1], z) for c, z in zip(corners, cz)], (0, 0, 1))
face(B["ceiling"], [(c[0], c[1], CEIL_Z) for c in corners], (0, 0, -1))
for (p0, p1), (_, u, nin) in zip(wl, lines):
    o0, o1 = p0 - 0.12 * nin - 0.12 * u, p1 - 0.12 * nin + 0.12 * u
    face(B["cap"], [(*p0, CEIL_Z + 0.01), (*p1, CEIL_Z + 0.01), (*o1, CEIL_Z + 0.01), (*o0, CEIL_Z + 0.01)], (0, 0, 1))
# Linear ceiling lights parallel to the front wall (single faces facing down, hidden from above).
for k in range(-4, 5):
    r0, r1 = -6.5, 6.5
    f = -0.3 + 1.2 * k * 0.0 + k * 1.15
    pa, pb = np.array(rf2xy(r0, f)), np.array(rf2xy(r1, f))
    for t0 in np.arange(0, 1, 0.25):
        q0, q1 = pa + (pb - pa) * (t0 + 0.02), pa + (pb - pa) * (t0 + 0.2)
        if not (inside(*q0, 0.6) and inside(*q1, 0.6)): continue
        w = 0.07 * F
        face(B["light"], [(*(q0 - w), -0.02), (*(q1 - w), -0.02), (*(q1 + w), -0.02), (*(q0 + w), -0.02)], (0, 0, -1))

# ---- walls with door openings, windows on the right wall, handrail on the left wall --------
def wall_quad(p0, nin, u, s0, s1, z0f, z1, key="wall"):
    a0, a1 = p0 + s0 * u, p0 + s1 * u
    za0 = fz(*a0) + z0f if z0f is not None else None
    za1 = fz(*a1) + z0f if z0f is not None else None
    face(B[key], [(*a0, za0), (*a1, za1), (*a1, z1 if z1 is not None else fz(*a1)), (*a0, z1 if z1 is not None else fz(*a0))], (*nin, 0))
win_wall = {"right": 2, "left": 0, "front": 1, "back": 3}.get(str(spec.get("windows_wall", "right")).lower(), 2)
rail_wall = {"right": 2, "left": 0, "front": 1, "back": 3}.get(str(spec.get("handrail_wall", "left")).lower(), 0)
for i, ((p0, p1), (_, u, nin)) in enumerate(zip(wl, lines)):
    L = float(np.linalg.norm(p1 - p0))
    cuts = sorted([(d["s"] - 0.5, d["s"] + 0.5) for d in doors if d["wall"] == i])
    s = 0.0
    for c0, c1 in cuts + [(L, L)]:
        if c0 > s:
            if i == win_wall:   # wall below and above a window band, glass with mullions
                for s_a in np.arange(s, c0, 1.5):
                    s_b = min(s_a + 1.5, c0)
                    a0, a1 = p0 + s_a * u, p0 + s_b * u
                    fa, fb = fz(*a0), fz(*a1)
                    top_a, top_b = min(fa + 2.45, CEIL_Z - 0.15), min(fb + 2.45, CEIL_Z - 0.15)
                    face(B["wall"], [(*a0, fa), (*a1, fb), (*a1, fb + 0.85), (*a0, fa + 0.85)], (*nin, 0))
                    face(B["glass"], [(*a0, fa + 0.85), (*a1, fb + 0.85), (*a1, top_b), (*a0, top_a)], (*nin, 0))
                    face(B["wall"], [(*a0, top_a), (*a1, top_b), (*a1, CEIL_Z), (*a0, CEIL_Z)], (*nin, 0))
                    m = a0 + 0.03 * nin
                    box(B["mullion"], (m[0], m[1], (fa + 0.85 + top_a) / 2), (0.06, 0.06, top_a - fa - 0.85), math.atan2(u[1], u[0]))
            else:
                a0, a1 = p0 + s * u, p0 + c0 * u
                face(B["wall"], [(*a0, fz(*a0)), (*a1, fz(*a1)), (*a1, CEIL_Z), (*a0, CEIL_Z)], (*nin, 0))
        if c1 > c0 and c0 < L:      # door opening: wall above, recessed door, frame, push bar, EXIT sign
            a0, a1 = p0 + c0 * u, p0 + c1 * u
            f0, f1 = fz(*a0), fz(*a1)
            face(B["wall"], [(*a0, f0 + 2.15), (*a1, f1 + 2.15), (*a1, CEIL_Z), (*a0, CEIL_Z)], (*nin, 0))
            d0, d1 = a0 - 0.06 * nin, a1 - 0.06 * nin
            face(B["door"], [(*d0, f0), (*d1, f1), (*d1, f1 + 2.15), (*d0, f0 + 2.15)], (*nin, 0))
            yaw = math.atan2(u[1], u[0]); mid = (a0 + a1) / 2; fm = fz(*mid)
            for sx in (c0, c1):
                q = p0 + sx * u
                box(B["frame"], (q[0], q[1], fz(*q) + 1.1), (0.06, 0.1, 2.2), yaw)
            box(B["frame"], (mid[0], mid[1], fm + 2.18), (1.06, 0.1, 0.06), yaw)
            bar = mid - 0.0 * nin
            box(B["steel"], (bar[0], bar[1], fm + 1.0), (0.8, 0.05, 0.05), yaw)
            sg = mid + 0.05 * nin
            box(B["exit"], (sg[0], sg[1], fm + 2.4), (0.38, 0.06, 0.16), yaw)
        s = max(s, c1)
    if i == rail_wall:
        for s_a in np.arange(0.4, L - 0.4, 0.5):
            q = p0 + s_a * u + 0.06 * nin
            if any(abs(s_a - d["s"]) < 0.7 for d in doors if d["wall"] == i): continue
            box(B["rail"], (q[0], q[1], fz(*q) + 0.9), (0.52, 0.05, 0.05), math.atan2(u[1], u[0]))

# ---- front wall furniture: pillar, screens, whiteboard, lectern --------------------------------
fw = 1  # wall index of the front wall (TR -> BR)
(p0, p1), (_, u, nin) = wl[fw], lines[fw]
yaw_fw = math.atan2(u[1], u[0])
def on_front(s, off): q = p0 + s * u + off * nin; return q, fz(*q)
q, f0 = on_front(1.6, 0.3); box(B["wall"], (q[0], q[1], (f0 + CEIL_Z) / 2), (0.6, 0.6, CEIL_Z - f0), yaw_fw)
for s_c in (4.3, 10.7):
    q, f0 = on_front(s_c, 0.04)
    box(B["black"], (q[0], q[1], f0 + 1.8), (2.6, 0.03, 1.6), yaw_fw)
    a0, a1 = p0 + (s_c - 1.2) * u + 0.07 * nin, p0 + (s_c + 1.2) * u + 0.07 * nin
    face(B["screen"], [(*a0, f0 + 1.07), (*a1, f0 + 1.07), (*a1, f0 + 2.53), (*a0, f0 + 2.53)], (*nin, 0),
         uv=lambda co, a0=a0, f0=f0: (float((np.array(co[:2]) - a0) @ u) / 2.4, (co.z - f0 - 1.07) / 1.46))
q, f0 = on_front(7.5, 0.03); box(B["board"], (q[0], q[1], f0 + 1.45), (3.0, 0.03, 1.2), yaw_fw)
box(B["frame"], (q[0], q[1], f0 + 0.84), (3.0, 0.12, 0.03), yaw_fw)
if spec.get("has_lectern", True):
    q, f0 = on_front(8.9, 1.1); box(B["lectern"], (q[0], q[1], f0 + 0.55), (0.7, 0.55, 1.1), yaw_fw)

# ---- curved desk rows and chairs ---------------------------------------------------------------
rc, fc = meas["center_rf"]
radii = sorted(r["radius"] for r in meas["rows"] if r["weight"] >= 0.1)
step = radii[1] - radii[0] if len(radii) > 1 else 1.35
for r in list(radii):     # rows the scan saw weakly (front and back) on the same spacing
    pass
want = int(spec.get("desk_rows", len(radii)) or len(radii))
base = radii[len(radii) // 2]
cands = sorted({round(base + k * 1.35, 2) for k in range(-6, 7)}, key=lambda x: abs(x - base))
rows = sorted([r for r in cands if r > 1.5 and any(inside(*rf2xy(rc + r * math.sin(t), fc - r * math.cos(t)), 1.0) for t in np.radians(np.arange(-80, 81, 5)))][:want])
print("rows", rows)
AISLE_DEG = -53.0
def arc_xy(rad, th): return rf2xy(rc + rad * math.sin(th), fc - rad * math.cos(th))
n_chairs = 0
for rad in rows:
    ths = np.radians(np.arange(-89, 89.01, 0.5))
    ok = [inside(*arc_xy(rad - 0.32, t), 0.9) and inside(*arc_xy(rad + 0.95, t), 0.9) and abs(math.degrees(t) - AISLE_DEG) * math.pi / 180 * rad > 0.55 for t in ths]
    segs, cur = [], []
    for t, g in zip(ths, ok):
        if g: cur.append(t)
        elif cur: segs.append(cur); cur = []
    if cur: segs.append(cur)
    for seg in segs:
        if (seg[-1] - seg[0]) * rad < 1.2: continue
        bmx = B["desk"]
        for t0, t1 in zip(seg[:-1], seg[1:]):
            pi0, po0, pi1, po1 = arc_xy(rad - 0.32, t0), arc_xy(rad + 0.28, t0), arc_xy(rad - 0.32, t1), arc_xy(rad + 0.28, t1)
            h0, h1 = fz(*arc_xy(rad, t0)) + 0.74, fz(*arc_xy(rad, t1)) + 0.74
            face(bmx, [(*pi0, h0), (*pi1, h1), (*po1, h1), (*po0, h0)], (0, 0, 1))
            face(bmx, [(*pi0, h0 - 0.04), (*pi1, h1 - 0.04), (*po1, h1 - 0.04), (*po0, h0 - 0.04)], (0, 0, -1))
            face(bmx, [(*po0, h0 - 0.04), (*po1, h1 - 0.04), (*po1, h1), (*po0, h0)], (0, 0, 0.0001))
            inn = np.array(arc_xy(rad - 0.5, (t0 + t1) / 2)) - np.array(arc_xy(rad, (t0 + t1) / 2))
            face(B["panel"], [(*pi0, fz(*pi0)), (*pi1, fz(*pi1)), (*pi1, h1), (*pi0, h0)], (*inn, 0))
        for t_end in (seg[0], seg[-1]):
            pi, po = arc_xy(rad - 0.32, t_end), arc_xy(rad + 0.28, t_end)
            h = fz(*arc_xy(rad, t_end)) + 0.74
            face(B["panel"], [(*pi, fz(*pi)), (*po, fz(*po)), (*po, h), (*pi, h)], (1, 0, 0))
        # chairs behind the desk, facing the front
        arc_len = (seg[-1] - seg[0]) * (rad + 0.7)
        k = max(1, int(arc_len / 0.78))
        for j in range(k):
            t = seg[0] + (j + 0.5) * (seg[-1] - seg[0]) / k
            x, y = arc_xy(rad + 0.72, t); fl = fz(x, y)
            cx, cy = arc_xy(0.0, t)
            yaw = math.atan2(cy - y, cx - x)      # local +x faces the front (arc center)
            fwd = np.array([math.cos(yaw), math.sin(yaw)]); side = np.array([-fwd[1], fwd[0]])
            box(B["chair"], (x, y, fl + 0.47), (0.46, 0.48, 0.07), yaw)
            bk = np.array([x, y]) - 0.24 * fwd
            box(B["chair"], (bk[0], bk[1], fl + 0.82), (0.06, 0.46, 0.52), yaw - 0.0)
            box(B["steel"], (x, y, fl + 0.25), (0.06, 0.06, 0.4), yaw)
            for sp_k in range(5):
                ang = yaw + sp_k * 2 * math.pi / 5
                c2 = np.array([x, y]) + 0.16 * np.array([math.cos(ang), math.sin(ang)])
                box(B["steel"], (c2[0], c2[1], fl + 0.04), (0.32, 0.04, 0.04), ang)
            for sgn in (-1, 1):
                ar = np.array([x, y]) + sgn * 0.25 * side
                box(B["chair"], (ar[0], ar[1], fl + 0.64), (0.34, 0.05, 0.04), yaw)
            n_chairs += 1
print("chairs", n_chairs)

# ---- objects, export ----------------------------------------------------------------------------
for k, bmx in B.items():
    if not bmx.faces: continue
    me = bpy.data.meshes.new(k); bmx.to_mesh(me); bmx.free()
    me.materials.append(M[k])
    ob = bpy.data.objects.new(k, me); bpy.context.scene.collection.objects.link(ob)
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", export_yup=True, export_normals=True,
                          export_materials="EXPORT", export_image_format="JPEG")
layout = {"walls": [[round(float(c[0]), 2), round(float(c[1]), 2)] for c in corners], "doors": []}
for d in doors:
    (p0, p1), (_, u, nin) = wl[d["wall"]], lines[d["wall"]]
    a0, a1 = p0 + (d["s"] - 0.5) * u, p0 + (d["s"] + 0.5) * u
    layout["doors"].append({"id": d["id"], "zone": d["zone"], "p1": [round(float(a0[0]), 2), round(float(a0[1]), 2)], "p2": [round(float(a1[0]), 2), round(float(a1[1]), 2)]})
json.dump(layout, open(LAYOUT, "w"), indent=1)
print("exported", OUT, json.dumps(layout))
