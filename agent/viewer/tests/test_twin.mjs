import assert from "node:assert/strict";
import test from "node:test";

import {
  cameraFramePath,
  doorAngles,
  doorOutward,
  doorStatus,
  exitZonePolygon,
  floorToScene,
  floorPointToThree,
  formatFps,
  meshTransform,
  normalizeMesh,
  transformMeshPoint,
  gridLines,
  normalizeConfig,
  normalizeState,
  predictPosition,
  smoothFactor,
  statsEntries,
  cameraView,
  clipPlaneFor,
  topView,
  viewButtons,
  wallPieces,
} from "../static/twin.js";
import { MOCK_CONFIG, cameraSees, createMockTwin, mockState } from "../static/twin-mock.js";
import * as THREE from "../static/vendor/three.module.min.js";

const ROOM = { width_m: 8, depth_m: 6, walls: [[0, 0], [8, 0], [8, 6], [0, 6]], doors: [{ id: "exit_a", p1: [3.4, 0], p2: [4.4, 0], zone: "exit_a" }] };
const close = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) < eps, `${a} != ${b}`);

test("floor y maps to scene -z", () => {
  assert.deepEqual(floorToScene(2, 3), { x: 2, z: -3 });
});

test("dead reckoning is capped at 300 ms", () => {
  const p = { x: 1, y: 1, vx: 2, vy: -1 };
  assert.deepEqual(predictPosition(p, 0), { x: 1, y: 1 });
  const mid = predictPosition(p, 100);
  close(mid.x, 1.2);
  close(mid.y, 0.9);
  const capped = predictPosition(p, 5000);
  close(capped.x, 1.6);
  close(capped.y, 0.7);
  assert.deepEqual(predictPosition(p, -50), { x: 1, y: 1 });
  assert.deepEqual(predictPosition({ x: 3, y: 4 }, 200), { x: 3, y: 4 });
});

test("smoothFactor stays in 0..1", () => {
  assert.equal(smoothFactor(0, 100), 0);
  assert.equal(smoothFactor(16, 0), 1);
  const k = smoothFactor(100, 100);
  assert.ok(k > 0.6 && k < 0.65);
});

test("door status labels, blocked wins", () => {
  assert.equal(doorStatus({ open: true, blocked: false }), "Open");
  assert.equal(doorStatus({ open: false, blocked: false }), "Closed");
  assert.equal(doorStatus({ open: true, blocked: true }), "Blocked");
  assert.equal(doorStatus({ open: false, blocked: true }), "Blocked");
  assert.equal(doorStatus(null), "Unknown");
});

test("door on the y=0 wall swings outward (toward -y)", () => {
  const door = ROOM.doors[0];
  const out = doorOutward(door, ROOM);
  close(out.normal[0], 0);
  close(out.normal[1], -1);
  const a = doorAngles(door, ROOM);
  close(a.closed, 0);
  close(a.length, 1);
  // open panel direction in floor coords is (cos, sin) of the angle
  close(Math.cos(a.open), 0);
  close(Math.sin(a.open), -1);
});

test("door on the far wall swings outward (toward +y)", () => {
  const door = { id: "d2", p1: [2, 6], p2: [3, 6] };
  const out = doorOutward(door, ROOM);
  close(out.normal[1], 1);
});

test("exit zone extends into the room", () => {
  const zone = exitZonePolygon(ROOM.doors[0], ROOM, 1.2);
  assert.deepEqual(zone[0], [3.4, 0]);
  assert.deepEqual(zone[1], [4.4, 0]);
  close(zone[2][1], 1.2);
  close(zone[3][1], 1.2);
  close(zone[2][0], 4.4);
});

test("walls close the loop and leave a gap at the door", () => {
  const pieces = wallPieces(ROOM.walls, ROOM.doors);
  assert.equal(pieces.length, 5);
  const front = pieces.filter(([a, b]) => a[1] === 0 && b[1] === 0);
  assert.equal(front.length, 2);
  close(front[0][0][0], 0);
  close(front[0][1][0], 3.4);
  close(front[1][0][0], 4.4);
  close(front[1][1][0], 8);
});

test("walls already closed are not doubled, off-wall doors are ignored", () => {
  const closed = [...ROOM.walls, [0, 0]];
  assert.equal(wallPieces(closed, []).length, 4);
  assert.equal(wallPieces(ROOM.walls, [{ id: "x", p1: [4, 3], p2: [5, 3] }]).length, 4);
  assert.deepEqual(wallPieces([], []), []);
});

test("grid lines every 0.5 m", () => {
  const lines = gridLines(2, 1, 0.5);
  assert.equal(lines.length, 5 + 3);
});

test("camera frame path encodes the id", () => {
  assert.equal(cameraFramePath("cam_1"), "/twin/camera/cam_1.jpg");
  assert.equal(cameraFramePath("a/b c"), "/twin/camera/a%2Fb%20c.jpg");
});

test("stats are flattened and shown as given", () => {
  assert.deepEqual(statsEntries({ frames_per_s: 14.6, cams: 2, nested: { p50_ms: 31 }, list: [1, 2], none: null }), [
    { label: "Frames per s", value: "14.6" },
    { label: "Cams", value: "2" },
    { label: "Nested p50 ms", value: "31" },
  ]);
  assert.deepEqual(statsEntries([{ label: "Tracker", value: 9.1, unit: "ms" }, { bad: 1 }]), [{ label: "Tracker", value: "9.1 ms" }]);
  assert.deepEqual(statsEntries(null), []);
  assert.equal(statsEntries({ a: 1, b: 2, c: 3 }, 2).length, 2);
});

test("fps formatting does not invent a value", () => {
  assert.equal(formatFps(null), "-");
  assert.equal(formatFps(undefined), "-");
  assert.equal(formatFps(14.96), "15.0");
  assert.equal(formatFps(7), "7.0");
});

test("normalizeConfig rejects junk and keeps valid parts", () => {
  assert.equal(normalizeConfig(null), null);
  assert.equal(normalizeConfig({ room: { width_m: 0, depth_m: 3 } }), null);
  const cfg = normalizeConfig({
    room: { width_m: 8, depth_m: 6, walls: [[0, 0], ["x", 1], [8, 0]], doors: [{ id: "d", p1: [1, 0], p2: [2, 0] }, { id: "bad" }] },
    cameras: [{ id: "c1", pose: { x: 1, y: 2, yaw_deg: 90 }, door_id: "d" }, { id: "c2", pose: { x: 1 } }],
  });
  assert.equal(cfg.room.walls.length, 2);
  assert.equal(cfg.room.doors.length, 1);
  assert.equal(cfg.room.doors[0].zone, "d");
  assert.equal(cfg.cameras.length, 1);
});

test("normalizeState drops bad rows and nulls missing numbers", () => {
  assert.equal(normalizeState(null), null);
  assert.equal(normalizeState([]), null);
  const s = normalizeState({
    t: 3,
    people: [{ id: "P-1", x: 1, y: 2 }, { id: "P-2", x: "a", y: 1 }],
    doors: [{ id: "exit_a", open: 1, blocked: true, obstruction_floor: [[0, 0], [1, 0]] }],
    cameras: [{ id: "cam_1", fps: "fast" }],
  });
  assert.deepEqual(s.people, [{ id: "P-1", x: 1, y: 2, vx: 0, vy: 0, cams: [] }]);
  assert.equal(s.doors[0].open, true);
  assert.equal(s.doors[0].obstruction_floor, null);
  assert.equal(s.cameras[0].fps, null);
  assert.equal(s.cameras[0].people_in_view, null);
});

test("top view fits the walls and looks straight down", () => {
  const cfg = normalizeConfig(MOCK_CONFIG);
  const v = topView(cfg, 1);
  close(v.target[0], 4);
  close(v.target[2], -3);
  assert.ok(v.position[1] > 10);
  close(v.position[0], 4, 1e-9);
  close(v.position[2], -3 + 0.01, 1e-9); // nudged toward screen-bottom (floor -y is three +z)
  close(v.halfWidth, v.halfHeight); // aspect 1
  assert.ok(v.halfWidth >= 4 && v.halfWidth < 4.5);
  const wide = topView(cfg, 2);
  close(wide.halfWidth / wide.halfHeight, 2);
  assert.ok(wide.halfWidth >= 4 && wide.halfHeight >= 3);
  nearArr(v.screenUp, [0, 0, -1]);
});

test("top_rotation_deg turns the room on screen", () => {
  const cfg = normalizeConfig({ ...MOCK_CONFIG, room: { ...MOCK_CONFIG.room, top_rotation_deg: 90 } });
  assert.equal(cfg.room.top_rotation_deg, 90);
  const v = topView(cfg, 1);
  // screen-up is floor +y turned 90 degrees counterclockwise: floor -x, three -x
  nearArr(v.screenUp, [-1, 0, 0]);
  close(v.target[0], 4);
  close(v.target[2], -3);
  close(v.position[0], 4 + 0.01);
});

test("camera view: pose and look_at in floor meters map to three.js position and target", () => {
  const cam = { id: "c", pose: { x: 1, y: 5, z: 2.6, yaw_deg: 0, look_at: [4, 1, 0.5], hfov_deg: 90 } };
  const v = cameraView(cam, 1);
  assert.deepEqual(v.position, [1, 2.6, -5]);
  assert.deepEqual(v.target, [4, 0.5, -1]);
  close(v.hfovDeg, 90);
  close(v.vfovDeg, 90); // aspect 1
  const wide = cameraView(cam, 16 / 9);
  close(Math.tan((wide.vfovDeg * Math.PI) / 360) * (16 / 9), Math.tan(Math.PI / 4));
});

test("camera view defaults: 2.0 m high, 70 degree hfov, aimed along yaw", () => {
  const v = cameraView({ id: "c", pose: { x: 0, y: 0, yaw_deg: 90 } }, 16 / 9);
  nearArr(v.position, [0, 2, 0]);
  nearArr(v.target, [0, 1, -3]); // 3 m along floor +y (three -z), 1 m high
  close(v.hfovDeg, 70);
  const bad = cameraView({ id: "c", pose: { x: 0, y: 0, yaw_deg: 0, hfov_deg: 400, look_at: [1, "x"] } }, 1);
  close(bad.hfovDeg, 70);
  nearArr(bad.target, [3, 1, 0]);
});

test("config keeps camera height, look_at, hfov and label", () => {
  const cfg = normalizeConfig({
    ...MOCK_CONFIG,
    cameras: [{ id: "cam_1", label: " Exit A ", pose: { x: 1, y: 2, yaw_deg: 0, z: 2.4, hfov_deg: 80, look_at: [3, 0, 0, 9] } }, { id: "cam_2", pose: { x: 1, y: 2, yaw_deg: 0, look_at: ["a", 1] } }],
  });
  assert.equal(cfg.cameras[0].label, "Exit A");
  assert.deepEqual(cfg.cameras[0].pose, { x: 1, y: 2, yaw_deg: 0, z: 2.4, hfov_deg: 80, look_at: [3, 0, 0] });
  assert.equal(cfg.cameras[1].label, null);
  assert.equal(cfg.cameras[1].pose.look_at, undefined);
  assert.deepEqual(viewButtons(cfg), [
    { view: "top", label: "Top" },
    { view: "cam:cam_1", label: "Exit A" },
    { view: "cam:cam_2", label: "cam_2" },
  ]);
});

test("scan clip plane keeps geometry at or below clip_height_m", () => {
  assert.deepEqual(clipPlaneFor(normalizeMesh({ url: "/r.glb" })), { normal: [0, -1, 0], constant: 2.3 });
  assert.deepEqual(clipPlaneFor(normalizeMesh({ url: "/r.glb", clip_height_m: 1.9 })), { normal: [0, -1, 0], constant: 1.9 });
  assert.equal(clipPlaneFor(normalizeMesh({ url: "/r.glb", clip_height_m: -1 })).constant, 2.3);
  assert.equal(clipPlaneFor(null).constant, 2.3);
  const { normal, constant } = clipPlaneFor(normalizeMesh({ url: "/r.glb", clip_height_m: 2 }));
  const plane = new THREE.Plane(new THREE.Vector3(...normal), constant);
  assert.ok(plane.distanceToPoint(new THREE.Vector3(3, 1.5, -2)) > 0, "below the cut is kept");
  assert.ok(plane.distanceToPoint(new THREE.Vector3(3, 2.5, -2)) < 0, "ceiling is clipped");
});
test("mock: door toggles every 6 s, exit blocked from 20 s to 40 s", () => {
  assert.equal(mockState(1).doors[0].open, false);
  assert.equal(mockState(7).doors[0].open, true);
  assert.equal(mockState(13).doors[0].open, false);
  assert.equal(mockState(19.9).doors[0].blocked, false);
  assert.equal(mockState(19.9).doors[0].obstruction_floor, null);
  assert.equal(mockState(20).doors[0].blocked, true);
  assert.equal(mockState(39.9).doors[0].blocked, true);
  assert.ok(mockState(30).doors[0].obstruction_floor.length >= 3);
  assert.equal(mockState(40).doors[0].blocked, false);
  assert.equal(mockState(85).doors[0].blocked, true);
});

test("mock: two people, view counts match, output passes normalization", () => {
  for (const t of [0, 5, 11, 23, 47]) {
    const raw = mockState(t);
    assert.equal(raw.people.length, 2);
    for (const cam of raw.cameras) {
      assert.equal(cam.people_in_view, raw.people.filter((p) => p.cams.includes(cam.id)).length);
      assert.equal(cam.fps, null);
    }
    const s = normalizeState(raw);
    assert.equal(s.people.length, 2);
    for (const p of s.people) assert.ok(p.x > 0 && p.x < 8 && p.y > 0.9 && p.y < 6);
  }
});

test("mock: velocity matches the path", () => {
  const a = mockState(10).people[0];
  const b = mockState(10.01).people[0];
  close((b.x - a.x) / 0.01, a.vx, 0.01);
  close((b.y - a.y) / 0.01, a.vy, 0.01);
});

test("mock camera field of view", () => {
  const cam = { pose: { x: 0, y: 0, yaw_deg: 0 } };
  assert.equal(cameraSees(cam, 2, 0), true);
  assert.equal(cameraSees(cam, 2, 2), false);
  assert.equal(cameraSees(cam, -2, 0), false);
});

test("mock source serves the four endpoints", async () => {
  let now = 1_000_000;
  const twin = createMockTwin(() => now);
  assert.equal(twin.mock, true);
  assert.ok(normalizeConfig(await twin.get("/twin/config")));
  now += 25_000;
  assert.equal((await twin.get("/twin/state")).doors[0].blocked, true);
  assert.ok(await twin.get("/twin/stats"));
  assert.equal(twin.frameUrl("cam_1"), null); // no canvas in node
  await assert.rejects(twin.get("/twin/other"));
});

test("mock clock offset starts the loop later", async () => {
  const twin = createMockTwin(() => 0, 21);
  assert.equal((await twin.get("/twin/state")).doors[0].blocked, true);
  const plain = createMockTwin(() => 0, Number.NaN);
  assert.equal((await plain.get("/twin/state")).doors[0].blocked, false);
});

const nearArr = (a, b, eps = 1e-9) => a.forEach((v, i) => close(v, b[i], eps));

test("floor coords map to three.js: y into the room is -z, z up is +y", () => {
  assert.deepEqual(floorPointToThree([1, 2, 3]), [1, 3, -2]);
  assert.deepEqual(floorPointToThree([4, 5]), [4, 0, -5]);
});

test("normalizeMesh applies defaults and refuses other hosts", () => {
  assert.deepEqual(normalizeMesh({ url: "/room.glb" }), { url: "/room.glb", scale: 1, rotation_deg: [0, 0, 0], offset: [0, 0, 0], opacity: 1, clip_height_m: 2.3 });
  assert.equal(normalizeMesh(null), null);
  assert.equal(normalizeMesh({ url: "https://example.com/room.glb" }), null);
  assert.equal(normalizeMesh({ url: "//example.com/room.glb" }), null);
  assert.equal(normalizeMesh({ url: "room.glb" }), null);
  const m = normalizeMesh({ url: "/a.glb", scale: -2, rotation_deg: [0, "x", 0], offset: [1, 2], opacity: 7 });
  assert.equal(m.scale, 1);
  assert.deepEqual(m.rotation_deg, [0, 0, 0]);
  assert.deepEqual(m.offset, [0, 0, 0]);
  assert.equal(m.opacity, 1);
  assert.deepEqual(normalizeMesh({ scale: [1, 2, 3] }, "/b.glb").scale, [1, 2, 3]);
  assert.equal(normalizeMesh({ url: "/a.glb", scale: 2 }, "/b.glb").url, "/b.glb");
  assert.equal(normalizeMesh({ url: "/a.glb", scale: 2 }, "/b.glb").scale, 2);
});

test("config keeps a valid room mesh and drops a bad one", () => {
  const cfg = normalizeConfig({ ...MOCK_CONFIG, room: { ...MOCK_CONFIG.room, mesh: { url: "/room.glb", scale: 1, rotation_deg: [0, 0, 90], offset: [0.5, 0, 0], opacity: 0.8 } } });
  assert.deepEqual(cfg.room.mesh.rotation_deg, [0, 0, 90]);
  assert.equal(normalizeConfig(MOCK_CONFIG).room.mesh, null);
  assert.equal(normalizeConfig({ ...MOCK_CONFIG, room: { ...MOCK_CONFIG.room, mesh: { url: "http://x/y.glb" } } }).room.mesh, null);
});

test("mesh offset is in floor meters", () => {
  const mesh = normalizeMesh({ url: "/r.glb", offset: [1, 2, 0.5] });
  assert.deepEqual(meshTransform(mesh).position, [1, 0.5, -2]);
  nearArr(transformMeshPoint([0, 0, 0], mesh), [1, 0.5, -2]);
});

test("yaw about floor up (rotation_deg z = 90) turns floor +x into floor +y", () => {
  const mesh = normalizeMesh({ url: "/r.glb", rotation_deg: [0, 0, 90] });
  // three +x is floor +x; floor +y is three -z
  nearArr(transformMeshPoint([1, 0, 0], mesh), floorPointToThree([0, 1, 0]));
});

test("scale multiplies before rotation and offset", () => {
  const mesh = normalizeMesh({ url: "/r.glb", scale: 2, rotation_deg: [0, 0, 90], offset: [1, 0, 0] });
  nearArr(transformMeshPoint([1, 0, 0], mesh), floorPointToThree([1, 2, 0]));
});

test("transform matches three.js Object3D for arbitrary settings", () => {
  const cases = [
    { scale: 1.5, rotation_deg: [10, -25, 40], offset: [0.3, 1.2, -0.1] },
    { scale: [1, 0.5, 2], rotation_deg: [-90, 0, 180], offset: [2, 3, 0] },
    { scale: 0.01, rotation_deg: [0, 45, 0], offset: [0, 0, 0] },
  ];
  for (const raw of cases) {
    const mesh = normalizeMesh({ url: "/r.glb", ...raw });
    const t = meshTransform(mesh);
    const obj = new THREE.Object3D();
    obj.scale.set(...t.scale);
    obj.rotation.set(t.rotation.x, t.rotation.y, t.rotation.z, t.rotation.order);
    obj.position.set(...t.position);
    obj.updateMatrixWorld(true);
    for (const p of [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0.7, -1.3, 2.2]]) {
      const v = new THREE.Vector3(...p).applyMatrix4(obj.matrixWorld);
      nearArr(transformMeshPoint(p, mesh), [v.x, v.y, v.z], 1e-9);
    }
  }
});
