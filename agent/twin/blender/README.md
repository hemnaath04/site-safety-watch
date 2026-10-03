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
