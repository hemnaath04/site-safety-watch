import assert from "node:assert/strict";
import test from "node:test";

import {
  cameraFramePath,
  doorAngles,
  doorOutward,
  doorStatus,
  exitZonePolygon,
  floorToScene,
  formatFps,
  gridLines,
  normalizeConfig,
  normalizeState,
  predictPosition,
  smoothFactor,
  statsEntries,
  viewPose,
  wallPieces,
} from "../static/twin.js";
import { MOCK_CONFIG, cameraSees, createMockTwin, mockState } from "../static/twin-mock.js";

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

test("view presets: top looks down, door looks at the first door from inside", () => {
  const cfg = normalizeConfig(MOCK_CONFIG);
  const top = viewPose("top", cfg);
  close(top.position[0], top.target[0]);
  assert.ok(top.position[1] > 5);
  const door = viewPose("door", cfg);
  close(door.target[0], 3.9);
  close(door.target[2], 0);
  assert.ok(door.position[2] < 0, "camera is inside the room (scene z negative)");
  const iso = viewPose("isometric", cfg);
  assert.ok(iso.position[1] > 3);
  assert.deepEqual(viewPose("door", { room: { ...cfg.room, doors: [] } }), viewPose("isometric", { room: { ...cfg.room, doors: [] } }));
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
