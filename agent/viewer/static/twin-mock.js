// In-browser fake of the twin service, used only with ?mock=1. Every value here is mock data.
const CYCLE_S = 60;
const BLOCK_FROM_S = 20;
const BLOCK_TO_S = 40;
const DOOR_TOGGLE_S = 6;
const CAMERA_HFOV_DEG = 70;
const CAMERA_RANGE_M = 9;

export const MOCK_CONFIG = Object.freeze({
  room: {
    width_m: 8,
    depth_m: 6,
    walls: [[0, 0], [8, 0], [8, 6], [0, 6]],
    doors: [{ id: "exit_a", p1: [3.4, 0], p2: [4.4, 0], zone: "exit_a" }],
  },
  cameras: [
    { id: "cam_1", pose: { x: 0.4, y: 5.6, yaw_deg: -58 }, door_id: "exit_a" },
    { id: "cam_2", pose: { x: 7.6, y: 5.6, yaw_deg: -123 }, door_id: "exit_a" },
  ],
});

const OBSTRUCTION = [[3.5, 0.3], [4.3, 0.3], [4.3, 0.9], [3.5, 0.9]];

function personAt(id, t) {
  if (id === "P-001") {
    const w = (2 * Math.PI) / 16;
    return {
      id,
      x: 4 + 2.6 * Math.cos(w * t),
      y: 3.4 + 1.6 * Math.sin(w * t),
      vx: -2.6 * w * Math.sin(w * t),
      vy: 1.6 * w * Math.cos(w * t),
    };
  }
  const w = (2 * Math.PI) / 22;
  return {
    id,
    x: 4 + 2.4 * Math.sin(w * t),
    y: 3.2 + 1.3 * Math.sin(2 * w * t),
    vx: 2.4 * w * Math.cos(w * t),
    vy: 2.6 * w * Math.cos(2 * w * t),
  };
}

export function cameraSees(camera, x, y) {
  const dx = x - camera.pose.x;
  const dy = y - camera.pose.y;
  const dist = Math.hypot(dx, dy);
  if (dist === 0 || dist > CAMERA_RANGE_M) return false;
  const bearing = Math.atan2(dy, dx);
  const yaw = (camera.pose.yaw_deg * Math.PI) / 180;
  const diff = Math.atan2(Math.sin(bearing - yaw), Math.cos(bearing - yaw));
  return Math.abs(diff) <= (CAMERA_HFOV_DEG * Math.PI) / 360;
}

export function mockState(elapsedS, startMs = 0) {
  const t = Math.max(0, elapsedS);
  const cycle = t % CYCLE_S;
  const blocked = cycle >= BLOCK_FROM_S && cycle < BLOCK_TO_S;
  const open = Math.floor(t / DOOR_TOGGLE_S) % 2 === 1;
  const cycleStart = t - cycle;
  const lastBlockChange = cycleStart + (cycle >= BLOCK_TO_S ? BLOCK_TO_S : cycle >= BLOCK_FROM_S ? BLOCK_FROM_S : 0);
  const lastToggle = Math.floor(t / DOOR_TOGGLE_S) * DOOR_TOGGLE_S;
  const updatedS = Math.max(lastBlockChange, lastToggle);

  const people = ["P-001", "P-002"].map((id) => {
    const p = personAt(id, t);
    p.cams = MOCK_CONFIG.cameras.filter((c) => cameraSees(c, p.x, p.y)).map((c) => c.id);
    return p;
  });

  return {
    t: new Date(startMs + t * 1000).toISOString(),
    people,
    doors: [{
      id: "exit_a",
      open,
      blocked,
      obstruction_floor: blocked ? OBSTRUCTION.map((pt) => [...pt]) : null,
      updated: new Date(startMs + updatedS * 1000).toISOString(),
    }],
    cameras: MOCK_CONFIG.cameras.map((c) => ({
      id: c.id,
      fps: null,
      people_in_view: people.filter((p) => p.cams.includes(c.id)).length,
      last_frame_age_ms: null,
    })),
  };
}

export const MOCK_STATS = Object.freeze({ note: "mock data, not measured" });

function drawFrame(cameraId, state) {
  if (typeof document === "undefined") return null;
  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 180;
  const ctx = canvas.getContext("2d");
  const grad = ctx.createLinearGradient(0, 0, 0, 180);
  grad.addColorStop(0, "#1a222b");
  grad.addColorStop(1, "#07090c");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, 320, 180);
  ctx.strokeStyle = "rgba(170,182,195,0.18)";
  for (let x = 0; x <= 320; x += 32) { ctx.beginPath(); ctx.moveTo(x, 110); ctx.lineTo(160 + (x - 160) * 2.2, 180); ctx.stroke(); }
  ctx.beginPath(); ctx.moveTo(0, 110); ctx.lineTo(320, 110); ctx.stroke();

  const camera = MOCK_CONFIG.cameras.find((c) => c.id === cameraId);
  if (camera) {
    const yaw = (camera.pose.yaw_deg * Math.PI) / 180;
    const half = (CAMERA_HFOV_DEG * Math.PI) / 360;
    for (const p of state.people) {
      if (!p.cams.includes(cameraId)) continue;
      const bearing = Math.atan2(p.y - camera.pose.y, p.x - camera.pose.x);
      const diff = Math.atan2(Math.sin(bearing - yaw), Math.cos(bearing - yaw));
      const dist = Math.hypot(p.x - camera.pose.x, p.y - camera.pose.y);
      const cx = 160 - (diff / half) * 160;
      const h = Math.min(150, 420 / Math.max(dist, 1));
      ctx.strokeStyle = "#57d6b1";
      ctx.lineWidth = 2;
      ctx.strokeRect(cx - h * 0.2, 150 - h, h * 0.4, h);
      ctx.fillStyle = "#57d6b1";
      ctx.font = "bold 11px system-ui, sans-serif";
      ctx.fillText(p.id, cx - h * 0.2, 146 - h);
    }
  }
  ctx.fillStyle = "rgba(243,240,233,0.85)";
  ctx.font = "bold 12px system-ui, sans-serif";
  ctx.fillText(`MOCK ${cameraId}`, 10, 18);
  return canvas.toDataURL("image/jpeg", 0.8);
}

export function createMockTwin(now = () => Date.now(), offsetS = 0) {
  const startMs = now();
  const offset = Number.isFinite(offsetS) && offsetS > 0 ? offsetS : 0;
  const elapsed = () => (now() - startMs) / 1000 + offset;
  const clone = (v) => JSON.parse(JSON.stringify(v));
  return {
    mock: true,
    async get(path) {
      if (path === "/twin/config") return clone(MOCK_CONFIG);
      if (path === "/twin/state") return mockState(elapsed(), startMs);
      if (path === "/twin/stats") return clone(MOCK_STATS);
      throw new Error(`mock has no ${path}`);
    },
    frameUrl(cameraId) {
      return drawFrame(cameraId, mockState(elapsed(), startMs));
    },
  };
}
