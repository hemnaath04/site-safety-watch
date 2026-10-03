# Headless scan cleanup: blender -b -P clean_scan.py -- <in.glb> <out.glb> <twin-config.json>
# Blender x, y = twin floor meters; Blender z = scan height (floor at FLOOR_Z).
import bmesh, bpy, json, sys, time
from collections import deque

args = sys.argv[sys.argv.index("--") + 1:]
src, dst, cfg_path = args[0], args[1], args[2]
FLOOR_Z = -2.25
KEEP_ABOVE_FLOOR_M = 3.2   # hard cap; the ceiling itself is removed by normal below
CEILING_FROM_Z = -0.9      # horizontal faces above this are ceiling, lights and soffits
WALL_MARGIN_M = 0.35       # keep the walls themselves, drop scan spill outside the room
DECIMATE_RATIO = 0.5
MIN_ISLAND_FACES = 400
TEX_SIZE = 4096
FLOOR_RGB = (0.07, 0.075, 0.09)

t0 = time.time()
walls = json.load(open(cfg_path))["room"]["walls"]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
for o in bpy.context.scene.objects:
    o.select_set(o.type == "MESH")
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
obj = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = obj.data
print("imported", len(me.vertices), "verts", len(me.polygons), "faces", "materials", [m.name for m in me.materials], f"{time.time()-t0:.1f}s")

# Inside test against the room polygon, grown by the margin (polygon is convex).
n = len(walls)
area = sum(walls[i][0] * walls[(i + 1) % n][1] - walls[(i + 1) % n][0] * walls[i][1] for i in range(n))
sign = 1 if area > 0 else -1
edges = []
for i in range(n):
    (x1, y1), (x2, y2) = walls[i], walls[(i + 1) % n]
    L = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
    edges.append((x1, y1, (x2 - x1) / L, (y2 - y1) / L))
def inside(x, y):
    for x1, y1, ux, uy in edges:
        if sign * (ux * (y - y1) - uy * (x - x1)) < -WALL_MARGIN_M:
            return False
    return True

bm = bmesh.new()
bm.from_mesh(me)
z_top = FLOOR_Z + KEEP_ABOVE_FLOOR_M
drop = [v for v in bm.verts if v.co.z > z_top or not inside(v.co.x, v.co.y)]
bmesh.ops.delete(bm, geom=drop, context="VERTS")
print("cropped: dropped", len(drop), "verts, left", len(bm.verts), f"{time.time()-t0:.1f}s")
bm.normal_update()
ceil = [f for f in bm.faces if abs(f.normal.z) > 0.6 and f.calc_center_median().z > CEILING_FROM_Z]
bmesh.ops.delete(bm, geom=ceil, context="FACES")
print("ceiling: dropped", len(ceil), "faces", f"{time.time()-t0:.1f}s")

# The hall floor is raked (about 0.5 m lower at the front). Fit a plane to upward faces near
# the floor so the fill under desks follows it.
import numpy as np
pts = np.array([f.calc_center_median()[:] for f in bm.faces if f.normal.z > 0.85 and f.calc_center_median().z < -2.0])
cells = {}
for x, y, z in pts:
    cells.setdefault((int(x // 1), int(y // 1)), []).append(z)
fl = np.array([(k[0] + 0.5, k[1] + 0.5, np.percentile(v, 10)) for k, v in cells.items() if len(v) > 30])
A = np.c_[fl[:, 0], fl[:, 1], np.ones(len(fl))]
coef = np.linalg.lstsq(A, fl[:, 2], rcond=None)[0]
floor_z = lambda x, y: float(coef[0] * x + coef[1] * y + coef[2])
print("floor fit z = %.4f x + %.4f y + %.3f" % tuple(coef), "corners", [round(floor_z(x, y), 2) for x, y in walls])

# Weld UV-seam duplicates first (UVs live on face corners, so they survive), then remove
# small floating islands (scan noise).
nv = len(bm.verts)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0005)
print("welded", nv - len(bm.verts), "duplicate verts", f"{time.time()-t0:.1f}s")
bm.faces.ensure_lookup_table()
seen = set()
small = []
for f in bm.faces:
    if f.index in seen:
        continue
    comp = [f]; seen.add(f.index); q = deque([f])
    while q:
        cur = q.popleft()
        for e in cur.edges:
            for g in e.link_faces:
                if g.index not in seen:
                    seen.add(g.index); comp.append(g); q.append(g)
    if len(comp) < MIN_ISLAND_FACES:
        small.extend(comp)
bmesh.ops.delete(bm, geom=small, context="FACES")
loose = [v for v in bm.verts if not v.link_faces]
bmesh.ops.delete(bm, geom=loose, context="VERTS")
bm.to_mesh(me); bm.free(); me.update()
print("islands: dropped", len(small), "faces, left", len(me.polygons), f"{time.time()-t0:.1f}s")

mod = obj.modifiers.new("dec", "DECIMATE")
mod.ratio = DECIMATE_RATIO
bpy.ops.object.modifier_apply(modifier=mod.name)
print("decimated to", len(me.polygons), "faces", f"{time.time()-t0:.1f}s")

for img in bpy.data.images:
    if img.size[0] > TEX_SIZE:
        print("texture", img.name, tuple(img.size), "->", TEX_SIZE)
        img.scale(TEX_SIZE, TEX_SIZE)

# Floor plane under the scan so holes under desks read as floor, not void.
scan_mat = me.materials[0] if me.materials else None
fmat = scan_mat.copy() if scan_mat else bpy.data.materials.new("floor")
fmat.name = "floor"
fmat.use_nodes = True
nt = fmat.node_tree
for node in list(nt.nodes):
    if node.type == "TEX_IMAGE":
        for link in list(node.outputs["Color"].links):
            rgb = nt.nodes.new("ShaderNodeRGB")
            rgb.outputs[0].default_value = (*FLOOR_RGB, 1)
            nt.links.new(rgb.outputs[0], link.to_socket)
        nt.nodes.remove(node)
fm = bpy.data.meshes.new("floor")
fm.from_pydata([(x, y, floor_z(x, y) - 0.05) for x, y in walls], [], [list(range(n)) if sign > 0 else list(reversed(range(n)))])
fm.materials.append(fmat)
fo = bpy.data.objects.new("floor", fm)
bpy.context.scene.collection.objects.link(fo)

kw = dict(filepath=dst, export_format="GLB", export_yup=True, export_apply=True, export_texcoords=True,
          export_normals=False, export_materials="EXPORT", export_image_format="JPEG")
try:
    bpy.ops.export_scene.gltf(**kw, export_jpeg_quality=88)
except TypeError:
    bpy.ops.export_scene.gltf(**kw)
print("exported", dst, f"{time.time()-t0:.1f}s")
