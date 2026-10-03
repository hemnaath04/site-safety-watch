# blender -b -P measure_scan.py -- data/room.glb out.json : desk-row arcs, floor fit, ceiling, from the scan
import bpy, bmesh, json, sys, numpy as np
src, out = sys.argv[sys.argv.index("--") + 1:][:2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
o = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
bm = bmesh.new(); bm.from_mesh(o.data); bm.transform(o.matrix_world); bm.normal_update()
P = np.array([f.calc_center_median()[:] for f in bm.faces]); N = np.array([f.normal[:] for f in bm.faces]); A = np.array([f.calc_area() for f in bm.faces])
fz = lambda x, y: -0.0437 * x - 0.0099 * y - 2.517
C = np.array([-0.29, 0.48]); F = np.array([0.956, 0.292]); R = np.array([0.292, -0.956])
d = P[:, :2] - C; pr = d @ R; pf = d @ F
h = P[:, 2] - fz(P[:, 0], P[:, 1])
up = np.abs(N[:, 2]) > 0.85
desk = up & (h > 0.62) & (h < 0.9) & (np.abs(pr) < 8.2) & (pf > -6) & (pf < 5.2)
print("desk faces", desk.sum())
dr, df, w = pr[desk], pf[desk], A[desk]
best = None
for r0 in np.arange(-4, 4.01, 0.25):
    for f0 in np.arange(2, 25, 0.5):
        rad = np.hypot(dr - r0, df - f0)
        hist, _ = np.histogram(rad, bins=np.arange(0, 40, 0.1), weights=w)
        s = (hist ** 2).sum()
        if best is None or s > best[0]: best = (s, r0, f0)
_, r0, f0 = best
rad = np.hypot(dr - r0, df - f0); ang = np.degrees(np.arctan2(dr - r0, -(df - f0)))  # 0 = straight back from center
hist, edges = np.histogram(rad, bins=np.arange(0, 40, 0.1), weights=w)
sm = np.convolve(hist, np.ones(3) / 3, mode="same")
peaks = [i for i in range(2, len(sm) - 2) if sm[i] == sm[i - 2:i + 3].max() and sm[i] > 0.12 * sm.max()]
rows = []
for i in peaks:
    rc = edges[i] + 0.05
    sel = np.abs(rad - rc) < 0.35
    a = ang[sel]
    ah, ae = np.histogram(a, bins=np.arange(-90, 90.1, 1), weights=w[sel])
    on = ah > 0.002
    segs = []; s0 = None; gap = 0
    for k, v in enumerate(on):
        if v:
            if s0 is None: s0 = k
            last = k; gap = 0
        elif s0 is not None:
            gap += 1
            if gap > 3: segs.append((ae[s0], ae[last + 1])); s0 = None; gap = 0
    if s0 is not None: segs.append((ae[s0], ae[last + 1]))
    segs = [(round(float(x), 1), round(float(y), 1)) for x, y in segs if y - x >= 4]
    rows.append({"radius": round(float(rc), 2), "weight": round(float(sm[i]), 2), "segments_deg": segs,
                 "desk_h": round(float(np.median(h[desk][sel])), 2)})
ceil = (N[:, 2] < -0.85) & (P[:, 2] > -1)
res = {"center_rf": [float(r0), float(f0)], "rows": rows, "ceiling_z_median": float(np.median(P[ceil, 2])) if ceil.any() else None}
print(json.dumps(res, indent=1)); json.dump(res, open(out, "w"), indent=1)
