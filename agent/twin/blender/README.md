# Room scan cleanup (headless Blender on the GB10)

```bash
blender -b -P agent/twin/blender/clean_scan.py -- data/room.glb data/room_clean.glb agent/twin/configs/twin-hall.json
```

Input: the one-time LiDAR scan (GLB, meters). The script keeps only the room inside the config
walls (plus a small margin), removes the ceiling and lights by face normal, welds UV-seam
duplicates and drops small floating islands, decimates by half, downsizes the texture to 4096,
and adds a floor fill fitted to the raked hall floor so gaps under desks read as floor.
Measured on the hall scan: 46 MB to 11 MB, 1.16 M to 0.31 M faces, about 15 s.

Point the viewer at the result with `TWIN_ROOM_GLB=data/room_clean.glb`. The twin config sets
`mesh.offset` z to 2.70 so the front of the hall (where both exits are) sits at floor height 0.

## Clean room model (default for the demo)

The raw scan has holes (missed floor, desks seen from one side, no front wall around the right
exit). `build_room.py` builds a clean, complete model instead, in about 4 s:

```bash
blender -b -P agent/twin/blender/measure_scan.py -- data/room.glb data/scan-measure.json
blender -b -P agent/twin/blender/build_room.py -- data/room.glb data/scan-measure.json \
  data/room-spec.json data/twin-hall.json data/screen_tex.jpg data/room_model.glb data/room-layout.json
```

- Layout from the scan: the four walls refit to the scan's wall surfaces, the raked floor plane,
  and the curved desk rows (common arc center and row radii found from the desk-top faces).
- Inventory and colors from `room-spec.json`, written by the local VLM from one frame of each
  camera (6 curved rows, windows on the right, handrail on the left, 2 screens, lectern).
  Measured: 4,978 ms, 964 prompt tokens, 251 completion tokens (2026-10-03 16:31).
- The projector screen texture is a crop of the camera footage (kept on the box, not in the repo).
- Walls and ceiling are single sided, so the Top view looks into the room and the camera views
  see a ceiling. Serve with `TWIN_ROOM_GLB=data/room_model.glb` (about 1 MB).
