const HEADER_BYTES = 4;
const POSITION_BYTES = 12;
const COLOR_BYTES = 3;
const FLAG_BYTES = 1;
const MAX_POINTS = 2_000_000;

export function parseSceneBuffer(buffer) {
  if (!(buffer instanceof ArrayBuffer) || buffer.byteLength < HEADER_BYTES) {
    throw new Error("scene payload is too short");
  }

  const view = new DataView(buffer);
  const headerLength = view.getUint32(0, true);
  const headerEnd = HEADER_BYTES + headerLength;
  if (headerLength === 0 || headerEnd > buffer.byteLength) {
    throw new Error("scene header length is invalid");
  }

  let header;
  try {
    header = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, HEADER_BYTES, headerLength)));
  } catch (_error) {
    throw new Error("scene header is not valid JSON");
  }

  const count = header?.count;
  if (!Number.isSafeInteger(count) || count < 0 || count > MAX_POINTS) {
    throw new Error("scene point count is invalid");
  }
  if (header.units !== "relative") {
    throw new Error("scene units are unsupported");
  }

  const positionsLength = count * POSITION_BYTES;
  const colorsLength = count * COLOR_BYTES;
  const flagsLength = count * FLAG_BYTES;
  const expectedLength = headerEnd + positionsLength + colorsLength + flagsLength;
  if (buffer.byteLength !== expectedLength) {
    throw new Error("scene payload length does not match its header");
  }

  const positions = new Float32Array(count * 3);
  let cursor = headerEnd;
  for (let index = 0; index < positions.length; index += 1) {
    const value = view.getFloat32(cursor, true);
    if (!Number.isFinite(value)) throw new Error("scene position is not finite");
    positions[index] = value;
    cursor += 4;
  }

  const colors = new Uint8Array(buffer.slice(cursor, cursor + colorsLength));
  cursor += colorsLength;
  const flags = new Uint8Array(buffer.slice(cursor, cursor + flagsLength));

  return { header, positions, colors, flags };
}
