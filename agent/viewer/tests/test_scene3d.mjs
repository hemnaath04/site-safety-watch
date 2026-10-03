import assert from "node:assert/strict";
import test from "node:test";

import { parseSceneBuffer } from "../static/scene3d-format.js";

function payload(header, positions = [], colors = [], flags = []) {
  const headerBytes = new TextEncoder().encode(JSON.stringify(header));
  const buffer = new ArrayBuffer(4 + headerBytes.length + positions.length * 4 + colors.length + flags.length);
  const view = new DataView(buffer);
  view.setUint32(0, headerBytes.length, true);
  new Uint8Array(buffer, 4, headerBytes.length).set(headerBytes);

  let cursor = 4 + headerBytes.length;
  for (const position of positions) {
    view.setFloat32(cursor, position, true);
    cursor += 4;
  }
  new Uint8Array(buffer, cursor, colors.length).set(colors);
  cursor += colors.length;
  new Uint8Array(buffer, cursor, flags.length).set(flags);
  return buffer;
}

test("parses an unaligned little-endian scene payload", () => {
  const buffer = payload(
    { count: 2, units: "relative", hfov_deg: 70, depth_ms: 42.5 },
    [0.5, -1, 2, 3.25, 4, -5],
    [12, 34, 56, 78, 90, 123],
    [0, 1],
  );

  const scene = parseSceneBuffer(buffer);
  assert.equal(scene.header.count, 2);
  assert.deepEqual([...scene.positions], [0.5, -1, 2, 3.25, 4, -5]);
  assert.deepEqual([...scene.colors], [12, 34, 56, 78, 90, 123]);
  assert.deepEqual([...scene.flags], [0, 1]);
});

test("rejects a payload whose count and byte length disagree", () => {
  const buffer = payload({ count: 2, units: "relative" });
  assert.throws(() => parseSceneBuffer(buffer), /length does not match/);
});

test("rejects unsupported units", () => {
  const buffer = payload({ count: 0, units: "meters" });
  assert.throws(() => parseSceneBuffer(buffer), /units are unsupported/);
});

test("rejects non-finite coordinates", () => {
  const buffer = payload(
    { count: 1, units: "relative" },
    [0, Number.NaN, 1],
    [0, 0, 0],
    [0],
  );
  assert.throws(() => parseSceneBuffer(buffer), /position is not finite/);
});
