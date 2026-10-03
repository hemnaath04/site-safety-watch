// Live 3D twin of the monitored exit. Renders only what the twin service returns.
// Floor coordinates are meters: x right, y into the room. Scene: (x, height, -y).

export const POLL_STATE_MS = 200;
export const POLL_FRAME_MS = 500;
export const POLL_STATS_MS = 5000;
export const RETRY_CONFIG_MS = 3000;
export const DEAD_RECKON_MAX_MS = 300;
export const OFFLINE_AFTER_FAILURES = 3;
export const WALL_HEIGHT_M = 2.6;
export const OBSTRUCTION_HEIGHT_M = 1;
export const EXIT_ZONE_DEPTH_M = 1.2;

const finite = (v) => typeof v === "number" && Number.isFinite(v);
const isPoint = (p) => Array.isArray(p) && p.length >= 2 && finite(p[0]) && finite(p[1]);
const isId = (v) => (typeof v === "string" && v.length > 0) || finite(v);

export function floorToScene(x, y) {
  return { x, z: -y };
}

export function predictPosition(person, ageMs, maxMs = DEAD_RECKON_MAX_MS) {
  const dt = Math.min(Math.max(ageMs, 0), maxMs) / 1000;
  return { x: person.x + (person.vx || 0) * dt, y: person.y + (person.vy || 0) * dt };
}

export function smoothFactor(dtMs, tauMs) {
  if (tauMs <= 0) return 1;
  return 1 - Math.exp(-Math.max(dtMs, 0) / tauMs);
}

export function doorStatus(door) {
  if (!door) return "Unknown";
  if (door.blocked) return "Blocked";
  return door.open ? "Open" : "Closed";
}

function roomCenter(room) {
  return [room.width_m / 2, room.depth_m / 2];
}

// Unit normal of the door line that points away from the room center (exits swing outward).
export function doorOutward(door, room) {
  const dx = door.p2[0] - door.p1[0];
  const dy = door.p2[1] - door.p1[1];
  const len = Math.hypot(dx, dy) || 1;
  const n = [-dy / len, dx / len];
  const [cx, cy] = roomCenter(room);
  const mx = (door.p1[0] + door.p2[0]) / 2 - cx;
  const my = (door.p1[1] + door.p2[1]) / 2 - cy;
  const s = Math.sign(n[0] * mx + n[1] * my) || 1;
  return { normal: [n[0] * s, n[1] * s], sign: s, length: len, angle: Math.atan2(dy, dx) };
}

// rotation.y for a panel hinged at p1 whose local +x runs toward p2 when closed.
export function doorAngles(door, room) {
  const o = doorOutward(door, room);
  return { closed: o.angle, open: o.angle + (o.sign * Math.PI) / 2, length: o.length };
}

export function exitZonePolygon(door, room, depth = EXIT_ZONE_DEPTH_M) {
  const { normal } = doorOutward(door, room);
  const ix = -normal[0] * depth;
  const iy = -normal[1] * depth;
  return [
    [door.p1[0], door.p1[1]],
    [door.p2[0], door.p2[1]],
    [door.p2[0] + ix, door.p2[1] + iy],
    [door.p1[0] + ix, door.p1[1] + iy],
  ];
}

// Splits the closed wall outline into segments with gaps where doors sit on a wall.
export function wallPieces(walls, doors = [], tolerance = 0.2) {
  if (!Array.isArray(walls) || walls.length < 2) return [];
  const pts = walls.slice();
  const first = pts[0];
  const last = pts[pts.length - 1];
  if (pts.length >= 3 && (first[0] !== last[0] || first[1] !== last[1])) pts.push(first);
  const pieces = [];
  for (let i = 0; i < pts.length - 1; i += 1) {
    const a = pts[i];
    const b = pts[i + 1];
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    const len = Math.hypot(dx, dy);
    if (len < 1e-6) continue;
    const ux = dx / len;
    const uy = dy / len;
    const cuts = [];
    for (const door of doors) {
      const proj = [door.p1, door.p2].map((p) => {
        const rx = p[0] - a[0];
        const ry = p[1] - a[1];
        return { t: rx * ux + ry * uy, d: Math.abs(rx * uy - ry * ux) };
      });
      if (proj.some((p) => p.d > tolerance)) continue;
      const lo = Math.max(0, Math.min(proj[0].t, proj[1].t));
      const hi = Math.min(len, Math.max(proj[0].t, proj[1].t));
      if (hi > lo) cuts.push([lo, hi]);
    }
    cuts.sort((p, q) => p[0] - q[0]);
    let cursor = 0;
    const at = (t) => [a[0] + ux * t, a[1] + uy * t];
    for (const [lo, hi] of cuts) {
      if (lo - cursor > 0.01) pieces.push([at(cursor), at(lo)]);
      cursor = Math.max(cursor, hi);
    }
    if (len - cursor > 0.01) pieces.push([at(cursor), at(len)]);
  }
  return pieces;
}

export function gridLines(width, depth, step = 0.5) {
  const out = [];
  for (let x = 0; x <= width + 1e-9; x += step) out.push([[x, 0], [x, depth]]);
  for (let y = 0; y <= depth + 1e-9; y += step) out.push([[0, y], [width, y]]);
  return out;
}

export function cameraFramePath(id) {
  return `/twin/camera/${encodeURIComponent(String(id))}.jpg`;
}

function humanize(key) {
  const text = String(key).replace(/[_.]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// Flattens the stats payload into label/value pairs, values shown as given.
export function statsEntries(stats, limit = 6) {
  const out = [];
  const push = (label, value) => {
    if (out.length < limit && value !== null && value !== undefined && typeof value !== "object") {
      out.push({ label, value: String(value) });
    }
  };
  if (Array.isArray(stats)) {
    for (const item of stats) {
      if (item && typeof item === "object" && "label" in item && "value" in item) {
        push(String(item.label), item.unit ? `${item.value} ${item.unit}` : item.value);
      }
    }
    return out;
  }
  if (!stats || typeof stats !== "object") return out;
  for (const [key, value] of Object.entries(stats)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      for (const [sub, v] of Object.entries(value)) push(humanize(`${key} ${sub}`), v);
    } else {
      push(humanize(key), value);
    }
  }
  return out;
}

export function normalizeConfig(raw) {
  const room = raw?.room;
  if (!room || !finite(room.width_m) || !finite(room.depth_m) || room.width_m <= 0 || room.depth_m <= 0) return null;
  const walls = Array.isArray(room.walls) ? room.walls.filter(isPoint).map((p) => [p[0], p[1]]) : [];
  const doors = Array.isArray(room.doors)
    ? room.doors.filter((d) => d && isId(d.id) && isPoint(d.p1) && isPoint(d.p2))
      .map((d) => ({ id: String(d.id), p1: [d.p1[0], d.p1[1]], p2: [d.p2[0], d.p2[1]], zone: d.zone ? String(d.zone) : String(d.id) }))
    : [];
  const cameras = Array.isArray(raw.cameras)
    ? raw.cameras.filter((c) => c && isId(c.id) && c.pose && finite(c.pose.x) && finite(c.pose.y) && finite(c.pose.yaw_deg))
      .map((c) => ({ id: String(c.id), pose: { x: c.pose.x, y: c.pose.y, yaw_deg: c.pose.yaw_deg }, door_id: c.door_id ?? null }))
    : [];
  return { room: { width_m: room.width_m, depth_m: room.depth_m, walls, doors }, cameras };
}

export function normalizeState(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const people = Array.isArray(raw.people)
    ? raw.people.filter((p) => p && isId(p.id) && finite(p.x) && finite(p.y))
      .map((p) => ({
        id: String(p.id),
        x: p.x,
        y: p.y,
        vx: finite(p.vx) ? p.vx : 0,
        vy: finite(p.vy) ? p.vy : 0,
        cams: Array.isArray(p.cams) ? p.cams.map(String) : [],
      }))
    : [];
  const doors = Array.isArray(raw.doors)
    ? raw.doors.filter((d) => d && isId(d.id)).map((d) => ({
      id: String(d.id),
      open: Boolean(d.open),
      blocked: Boolean(d.blocked),
      obstruction_floor: Array.isArray(d.obstruction_floor) && d.obstruction_floor.filter(isPoint).length >= 3
        ? d.obstruction_floor.filter(isPoint).map((p) => [p[0], p[1]])
        : null,
      updated: d.updated ?? null,
    }))
    : [];
  const cameras = Array.isArray(raw.cameras)
    ? raw.cameras.filter((c) => c && isId(c.id)).map((c) => ({
      id: String(c.id),
      fps: finite(c.fps) ? c.fps : null,
      people_in_view: finite(c.people_in_view) ? c.people_in_view : null,
      last_frame_age_ms: finite(c.last_frame_age_ms) ? c.last_frame_age_ms : null,
    }))
    : [];
  return { t: raw.t ?? null, people, doors, cameras };
}

// Fixed camera presets in scene coordinates.
export function viewPose(name, config) {
  const { width_m: w, depth_m: d } = config.room;
  const r = Math.max(w, d);
  const c = { x: w / 2, y: 0, z: -d / 2 };
  if (name === "top") {
    return { position: [c.x, r * 1.55, c.z + 0.001], target: [c.x, 0, c.z] };
  }
  const door = config.room.doors[0];
  if (name === "door" && door) {
    const { normal } = doorOutward(door, config.room);
    const mx = (door.p1[0] + door.p2[0]) / 2;
    const my = (door.p1[1] + door.p2[1]) / 2;
    const back = Math.min(5, d * 0.85);
    const px = mx - normal[0] * back;
    const py = my - normal[1] * back;
    return { position: [px, 3.1, -py], target: [mx, 0.7, -my] };
  }
  return { position: [c.x + r * 0.62, r * 0.85, c.z - r * 0.95], target: [c.x, 0, c.z + d * 0.08] };
}

export function formatFps(fps) {
  return fps === null || fps === undefined ? "-" : (Math.round(fps * 10) / 10).toFixed(1);
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  boot().catch((error) => {
    const empty = document.querySelector("#twin-empty");
    if (empty) {
      empty.hidden = false;
      empty.querySelector("p").textContent = "The 3D view could not start.";
      empty.querySelector(":scope > span").textContent = String(error?.message || error);
    }
  });
}

async function boot() {
  const THREE = await import("./vendor/three.module.min.js");
  const { OrbitControls } = await import("./vendor/OrbitControls.js");
  const params = new URLSearchParams(window.location.search);
  const mockMode = params.get("mock") === "1";
  const startView = ["isometric", "top", "door"].includes(params.get("view")) ? params.get("view") : "isometric";
  const source = mockMode ? (await import("./twin-mock.js")).createMockTwin(undefined, Number(params.get("at"))) : liveSource();
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const css = getComputedStyle(document.documentElement);
  const color = (name, fallback) => new THREE.Color(css.getPropertyValue(name).trim() || fallback);
  const HAZARD = color("--hazard", "#ff6a32");
  const RESOLVED = color("--resolved", "#57d6b1");
  const TEXT = color("--text", "#f3f0e9");
  const RULE = color("--rule-strong", "#3b4856");

  const el = {
    stage: document.querySelector("#twin-stage"),
    canvas: document.querySelector("#twin-canvas"),
    labels: document.querySelector("#twin-labels"),
    empty: document.querySelector("#twin-empty"),
    banner: document.querySelector("#twin-banner"),
    bannerZone: document.querySelector("#twin-banner-zone"),
    state: document.querySelector("#twin-state"),
    updated: document.querySelector("#twin-updated"),
    people: document.querySelector("#hud-people"),
    doors: document.querySelector("#hud-doors"),
    cameras: document.querySelector("#camera-list"),
    camerasEmpty: document.querySelector("#camera-empty"),
    stats: document.querySelector("#twin-stats"),
    statsLabel: document.querySelector("#twin-stats-label"),
    statsList: document.querySelector("#twin-stats-list"),
    views: [...document.querySelectorAll("[data-view]")],
  };

  if (mockMode) document.body.dataset.mock = "1";

  const renderer = new THREE.WebGLRenderer({ canvas: el.canvas, antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(new THREE.Color("#07090c"));
  const scene = new THREE.Scene();
  scene.fog = new THREE.Fog(0x07090c, 18, 40);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 200);
  camera.position.set(8, 8, 8);
  const controls = new OrbitControls(camera, el.canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.12;
  controls.maxPolarAngle = Math.PI / 2 - 0.02;
  controls.minDistance = 1.5;
  controls.maxDistance = 40;

  scene.add(new THREE.HemisphereLight(0xdfe8f2, 0x0b0f14, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.4);
  sun.position.set(6, 12, 4);
  scene.add(sun);

  const roomGroup = new THREE.Group();
  const peopleGroup = new THREE.Group();
  scene.add(roomGroup, peopleGroup);

  let config = null;
  let doorViews = new Map();
  let cameraViews = new Map();
  const people = new Map();
  let failures = 0;
  let online = false;

  const resize = () => {
    const { clientWidth: w, clientHeight: h } = el.stage;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(el.stage);
  resize();

  function setStatus(kind, text) {
    el.state.dataset.state = kind;
    el.state.querySelector("span:last-child").textContent = text;
  }

  function setEmpty(show, title, detail) {
    el.empty.hidden = !show;
    if (show) {
      el.empty.querySelector("p").textContent = title;
      el.empty.querySelector(":scope > span").textContent = detail;
    }
  }

  function makeLabel(text, kind) {
    const node = document.createElement("div");
    node.className = `twin-label twin-label-${kind}`;
    node.textContent = text;
    el.labels.append(node);
    return node;
  }

  function floorShape(points) {
    const shape = new THREE.Shape();
    points.forEach(([x, y], i) => (i === 0 ? shape.moveTo(x, y) : shape.lineTo(x, y)));
    shape.closePath();
    return shape;
  }

  function flatOnFloor(object, height = 0) {
    object.rotation.x = -Math.PI / 2;
    object.position.y = height;
    return object;
  }

  function outline(points, material, height) {
    const verts = points.map(([x, y]) => new THREE.Vector3(x, height, -y));
    return new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(verts), material);
  }

  const shadowTexture = (() => {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const g = c.getContext("2d");
    const grad = g.createRadialGradient(32, 32, 2, 32, 32, 32);
    grad.addColorStop(0, "rgba(0,0,0,0.75)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  })();

  function clearGroup(group) {
    for (const child of [...group.children]) {
      group.remove(child);
      child.traverse((o) => {
        o.geometry?.dispose();
        if (o.material && o.material.map !== shadowTexture) o.material.dispose?.();
      });
    }
  }

  function buildRoom(cfg) {
    clearGroup(roomGroup);
    for (const v of cameraViews.values()) v.label.remove();
    for (const v of doorViews.values()) v.label.remove();
    doorViews = new Map();
    cameraViews = new Map();
    const { room } = cfg;

    const floor = flatOnFloor(new THREE.Mesh(
      new THREE.PlaneGeometry(room.width_m, room.depth_m),
      new THREE.MeshStandardMaterial({ color: 0x0e1319, roughness: 0.95 }),
    ));
    floor.position.set(room.width_m / 2, 0, -room.depth_m / 2);
    roomGroup.add(floor);

    const gridVerts = [];
    for (const [[x1, y1], [x2, y2]] of gridLines(room.width_m, room.depth_m, 0.5)) {
      gridVerts.push(x1, 0.002, -y1, x2, 0.002, -y2);
    }
    const gridGeo = new THREE.BufferGeometry();
    gridGeo.setAttribute("position", new THREE.Float32BufferAttribute(gridVerts, 3));
    roomGroup.add(new THREE.LineSegments(gridGeo, new THREE.LineBasicMaterial({ color: 0x27313c, transparent: true, opacity: 0.7 })));

    const wallMat = new THREE.MeshStandardMaterial({ color: RULE, transparent: true, opacity: 0.22, depthWrite: false, side: THREE.DoubleSide });
    const wallEdge = new THREE.LineBasicMaterial({ color: 0x82909f, transparent: true, opacity: 0.55 });
    for (const [[x1, y1], [x2, y2]] of wallPieces(room.walls, room.doors)) {
      const len = Math.hypot(x2 - x1, y2 - y1);
      const geo = new THREE.BoxGeometry(len, WALL_HEIGHT_M, 0.1);
      const mesh = new THREE.Mesh(geo, wallMat);
      mesh.position.set((x1 + x2) / 2, WALL_HEIGHT_M / 2, -(y1 + y2) / 2);
      mesh.rotation.y = Math.atan2(y2 - y1, x2 - x1);
      mesh.renderOrder = 2;
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geo), wallEdge);
      mesh.add(edges);
      roomGroup.add(mesh);
    }

    for (const door of room.doors) {
      const angles = doorAngles(door, room);
      const pivot = new THREE.Group();
      pivot.position.set(door.p1[0], 0, -door.p1[1]);
      pivot.rotation.y = angles.closed;
      const panelGeo = new THREE.BoxGeometry(angles.length - 0.04, 2.1, 0.05);
      const panelMat = new THREE.MeshStandardMaterial({ color: 0xc9d2dc, roughness: 0.6, metalness: 0.1 });
      const panel = new THREE.Mesh(panelGeo, panelMat);
      panel.position.set(angles.length / 2, 1.05, 0);
      panel.add(new THREE.LineSegments(new THREE.EdgesGeometry(panelGeo), new THREE.LineBasicMaterial({ color: 0x0b0f14 })));
      pivot.add(panel);
      roomGroup.add(pivot);

      const zonePts = exitZonePolygon(door, room);
      const zoneMat = new THREE.MeshBasicMaterial({ color: RESOLVED, transparent: true, opacity: 0.16, depthWrite: false });
      const zone = flatOnFloor(new THREE.Mesh(new THREE.ShapeGeometry(floorShape(zonePts)), zoneMat), 0.006);
      const zoneLineMat = new THREE.LineBasicMaterial({ color: RESOLVED, transparent: true, opacity: 0.9 });
      const zoneLine = outline(zonePts, zoneLineMat, 0.008);
      roomGroup.add(zone, zoneLine);

      const mid = [(door.p1[0] + door.p2[0]) / 2, (door.p1[1] + door.p2[1]) / 2];
      const label = makeLabel(door.zone, "door");
      doorViews.set(door.id, {
        door, pivot, angles, current: angles.closed, zoneMat, zoneLineMat,
        obstruction: null, obstructionKey: "", blocked: false,
        label, anchor: new THREE.Vector3(mid[0], 2.35, -mid[1]),
      });
    }

    for (const cam of cfg.cameras) {
      const group = new THREE.Group();
      group.position.set(cam.pose.x, 2.45, -cam.pose.y);
      group.rotation.y = (cam.pose.yaw_deg * Math.PI) / 180;
      const tilt = new THREE.Group();
      tilt.rotation.z = -0.35;
      group.add(tilt);
      const body = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.12, 0.12), new THREE.MeshStandardMaterial({ color: 0xe6edf3 }));
      tilt.add(body);
      const reach = 1.3;
      const hw = Math.tan((35 * Math.PI) / 180) * reach;
      const hh = Math.tan((22 * Math.PI) / 180) * reach;
      const o = [0.11, 0, 0];
      const corners = [[reach, hh, hw], [reach, hh, -hw], [reach, -hh, -hw], [reach, -hh, hw]];
      const tri = [];
      for (let i = 0; i < 4; i += 1) tri.push(...o, ...corners[i], ...corners[(i + 1) % 4]);
      const coneGeo = new THREE.BufferGeometry();
      coneGeo.setAttribute("position", new THREE.Float32BufferAttribute(tri, 3));
      tilt.add(new THREE.Mesh(coneGeo, new THREE.MeshBasicMaterial({ color: 0x9dc6ff, transparent: true, opacity: 0.1, side: THREE.DoubleSide, depthWrite: false })));
      const lines = [];
      for (let i = 0; i < 4; i += 1) lines.push(...o, ...corners[i], ...corners[i], ...corners[(i + 1) % 4]);
      const lineGeo = new THREE.BufferGeometry();
      lineGeo.setAttribute("position", new THREE.Float32BufferAttribute(lines, 3));
      tilt.add(new THREE.LineSegments(lineGeo, new THREE.LineBasicMaterial({ color: 0x9dc6ff, transparent: true, opacity: 0.75 })));
      roomGroup.add(group);
      cameraViews.set(cam.id, { label: makeLabel(cam.id, "camera"), anchor: new THREE.Vector3(cam.pose.x, 2.75, -cam.pose.y) });
    }
  }

  function setObstruction(view, polygon) {
    const key = polygon ? JSON.stringify(polygon) : "";
    if (key === view.obstructionKey) return;
    view.obstructionKey = key;
    if (view.obstruction) {
      roomGroup.remove(view.obstruction);
      view.obstruction.traverse((o) => { o.geometry?.dispose(); o.material?.dispose?.(); });
      view.obstruction = null;
    }
    if (!polygon) return;
    const geo = new THREE.ExtrudeGeometry(floorShape(polygon), { depth: OBSTRUCTION_HEIGHT_M, bevelEnabled: false });
    const mesh = flatOnFloor(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: HAZARD, emissive: HAZARD, emissiveIntensity: 0.35, transparent: true, opacity: 0.82 })));
    mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({ color: 0xffd9cb })));
    view.obstruction = mesh;
    roomGroup.add(mesh);
  }

  function makePerson(p) {
    const group = new THREE.Group();
    const body = new THREE.Mesh(
      new THREE.CapsuleGeometry(0.21, 1.16, 6, 16),
      new THREE.MeshStandardMaterial({ color: TEXT, roughness: 0.55, emissive: 0x1a222b }),
    );
    body.position.y = 0.21 + 0.58;
    const shadow = flatOnFloor(new THREE.Mesh(
      new THREE.PlaneGeometry(0.9, 0.9),
      new THREE.MeshBasicMaterial({ map: shadowTexture, transparent: true, depthWrite: false }),
    ), 0.01);
    group.add(body, shadow);
    peopleGroup.add(group);
    return { group, label: makeLabel(p.id, "person"), target: p, recvAt: performance.now(), disp: { x: p.x, y: p.y }, fresh: true };
  }

  function clearPeople() {
    for (const v of people.values()) {
      peopleGroup.remove(v.group);
      v.group.traverse((o) => { o.geometry?.dispose(); if (o.material?.map !== shadowTexture) o.material?.dispose?.(); });
      v.label.remove();
    }
    people.clear();
  }

  function applyState(state) {
    const now = performance.now();
    const seen = new Set();
    for (const p of state.people) {
      seen.add(p.id);
      let v = people.get(p.id);
      if (!v) {
        v = makePerson(p);
        people.set(p.id, v);
      } else {
        v.target = p;
        v.recvAt = now;
      }
    }
    for (const [id, v] of people) {
      if (!seen.has(id)) {
        peopleGroup.remove(v.group);
        v.label.remove();
        people.delete(id);
      }
    }

    const doorStates = new Map(state.doors.map((d) => [d.id, d]));
    const blockedZones = [];
    for (const [id, view] of doorViews) {
      const ds = doorStates.get(id);
      view.state = ds || null;
      view.blocked = Boolean(ds?.blocked);
      setObstruction(view, ds?.blocked ? ds.obstruction_floor : null);
      if (view.blocked) blockedZones.push(view.door.zone);
    }
    el.banner.hidden = blockedZones.length === 0;
    el.bannerZone.textContent = blockedZones.join(", ");
    renderHud(state);
  }

  function renderHud(state) {
    el.people.textContent = state ? String(state.people.length) : "-";
    el.doors.replaceChildren();
    for (const door of config?.room.doors || []) {
      const ds = state?.doors.find((d) => d.id === door.id);
      const status = state && ds ? doorStatus(ds) : "No data";
      const row = document.createElement("li");
      row.className = "hud-door";
      row.dataset.status = status.toLowerCase().replace(/\s+/g, "-");
      const name = document.createElement("span");
      name.textContent = door.zone;
      const chip = document.createElement("strong");
      chip.textContent = status;
      row.append(name, chip);
      el.doors.append(row);
    }
    const camStates = new Map((state?.cameras || []).map((c) => [c.id, c]));
    for (const card of el.cameras.querySelectorAll("[data-camera]")) {
      const cs = camStates.get(card.dataset.camera);
      card.querySelector(".cam-fps").textContent = formatFps(cs?.fps);
      card.querySelector(".cam-people").textContent = cs?.people_in_view ?? "-";
    }
  }

  function buildCameraList(cfg) {
    el.cameras.replaceChildren();
    el.camerasEmpty.hidden = cfg.cameras.length > 0;
    for (const cam of cfg.cameras) {
      const card = document.createElement("figure");
      card.className = "cam-card";
      card.dataset.camera = cam.id;
      const frame = document.createElement("div");
      frame.className = "cam-frame";
      const img = document.createElement("img");
      img.alt = `Latest frame from camera ${cam.id} with detections drawn`;
      img.hidden = true;
      const wait = document.createElement("span");
      wait.className = "cam-wait";
      wait.textContent = "Waiting for frame";
      frame.append(img, wait);
      const caption = document.createElement("figcaption");
      caption.innerHTML = '<strong class="cam-id"></strong><dl><div><dt>fps</dt><dd class="cam-fps">-</dd></div><div><dt>In view</dt><dd class="cam-people">-</dd></div></dl>';
      caption.querySelector(".cam-id").textContent = cam.id;
      card.append(frame, caption);
      el.cameras.append(card);
    }
  }

  function refreshFrames() {
    if (config && online) {
      for (const card of el.cameras.querySelectorAll("[data-camera]")) {
        const url = source.frameUrl(card.dataset.camera);
        if (!url) continue;
        const img = card.querySelector("img");
        const wait = card.querySelector(".cam-wait");
        const loader = new Image();
        loader.onload = () => { img.src = loader.src; img.hidden = false; wait.hidden = true; };
        loader.onerror = () => { img.hidden = true; wait.hidden = false; wait.textContent = "No frame"; };
        loader.src = url;
      }
    }
    setTimeout(refreshFrames, POLL_FRAME_MS);
  }

  async function loadConfig() {
    try {
      const cfg = normalizeConfig(await source.get("/twin/config"));
      if (!cfg) throw new Error("twin config is not valid");
      config = cfg;
      buildRoom(cfg);
      buildCameraList(cfg);
      renderHud(null);
      goToView(startView, true);
      setStatus("checking", "Waiting for live state");
      setEmpty(true, "Waiting for live state.", "The twin service answered. People and doors appear with the first state update.");
      pollState();
      pollStats();
    } catch (_error) {
      setStatus("offline", "Twin service offline");
      setEmpty(true, "Twin service offline.", "Nothing is shown until the twin service on this box answers. Retrying.");
      setTimeout(loadConfig, RETRY_CONFIG_MS);
    }
  }

  async function pollState() {
    const started = performance.now();
    try {
      const state = normalizeState(await source.get("/twin/state"));
      if (!state) throw new Error("twin state is not valid");
      failures = 0;
      if (!online) {
        online = true;
        setStatus(source.mock ? "mock" : "online", source.mock ? "Mock data" : "Twin live");
        setEmpty(false);
      }
      applyState(state);
      el.updated.textContent = `Updated ${new Date().toLocaleTimeString([], { hour12: false })}`;
    } catch (_error) {
      failures += 1;
      if (failures >= OFFLINE_AFTER_FAILURES && online) {
        online = false;
        clearPeople();
        for (const view of doorViews.values()) { view.blocked = false; view.state = null; setObstruction(view, null); }
        el.banner.hidden = true;
        renderHud(null);
        setStatus("offline", "Twin service offline");
        setEmpty(true, "Twin service offline.", "Live state stopped. Nothing is shown until the twin service answers again.");
      }
    }
    setTimeout(pollState, Math.max(0, POLL_STATE_MS - (performance.now() - started)));
  }

  async function pollStats() {
    try {
      const entries = statsEntries(await source.get("/twin/stats"));
      el.statsLabel.textContent = source.mock ? "Mock data, not measured" : "Measured on the GB10";
      el.statsList.replaceChildren(...entries.map(({ label, value }) => {
        const item = document.createElement("div");
        item.className = "metric";
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = value;
        item.append(dt, dd);
        return item;
      }));
      el.stats.hidden = entries.length === 0;
    } catch (_error) {
      el.stats.hidden = true;
    }
    setTimeout(pollStats, POLL_STATS_MS);
  }

  let tween = null;
  function goToView(name, instant = false) {
    if (!config) return;
    const pose = viewPose(name, config);
    for (const b of el.views) b.setAttribute("aria-pressed", String(b.dataset.view === name));
    const to = { p: new THREE.Vector3(...pose.position), t: new THREE.Vector3(...pose.target) };
    if (instant || reducedMotion.matches) {
      camera.position.copy(to.p);
      controls.target.copy(to.t);
      controls.update();
      tween = null;
      return;
    }
    tween = { from: { p: camera.position.clone(), t: controls.target.clone() }, to, start: performance.now(), ms: 550 };
  }
  for (const b of el.views) b.addEventListener("click", () => goToView(b.dataset.view));
  controls.addEventListener("start", () => {
    tween = null;
    for (const b of el.views) b.setAttribute("aria-pressed", "false");
  });

  const projected = new THREE.Vector3();
  function placeLabel(node, anchor) {
    projected.copy(anchor).project(camera);
    const visible = projected.z < 1 && Math.abs(projected.x) < 1.1 && Math.abs(projected.y) < 1.1;
    node.hidden = !visible;
    if (!visible) return;
    const x = (projected.x * 0.5 + 0.5) * el.stage.clientWidth;
    const y = (-projected.y * 0.5 + 0.5) * el.stage.clientHeight;
    node.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -100%)`;
  }

  let lastFrame = performance.now();
  const anchor = new THREE.Vector3();
  function frame(now) {
    const dt = now - lastFrame;
    lastFrame = now;

    if (tween) {
      const k = Math.min(1, (now - tween.start) / tween.ms);
      const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      camera.position.lerpVectors(tween.from.p, tween.to.p, e);
      controls.target.lerpVectors(tween.from.t, tween.to.t, e);
      if (k >= 1) tween = null;
    }

    for (const v of people.values()) {
      const pred = predictPosition(v.target, now - v.recvAt);
      if (v.fresh || Math.hypot(pred.x - v.disp.x, pred.y - v.disp.y) > 2) {
        v.disp = pred;
        v.fresh = false;
      } else {
        const k = smoothFactor(dt, 90);
        v.disp.x += (pred.x - v.disp.x) * k;
        v.disp.y += (pred.y - v.disp.y) * k;
      }
      const s = floorToScene(v.disp.x, v.disp.y);
      v.group.position.set(s.x, 0, s.z);
      placeLabel(v.label, anchor.set(s.x, 1.85, s.z));
    }

    const pulse = reducedMotion.matches ? 1 : 0.5 + 0.5 * Math.sin((now / 1000) * Math.PI * 2 * 0.9);
    for (const view of doorViews.values()) {
      const open = Boolean(view.state?.open);
      const target = open ? view.angles.open : view.angles.closed;
      view.current += (target - view.current) * (reducedMotion.matches ? 1 : smoothFactor(dt, 160));
      view.pivot.rotation.y = view.current;
      if (view.blocked) {
        view.zoneMat.color.copy(HAZARD);
        view.zoneMat.opacity = 0.3 + 0.4 * pulse;
        view.zoneLineMat.color.copy(HAZARD);
      } else {
        view.zoneMat.color.copy(RESOLVED);
        view.zoneMat.opacity = 0.16;
        view.zoneLineMat.color.copy(RESOLVED);
      }
      view.label.dataset.blocked = String(view.blocked);
      placeLabel(view.label, view.anchor);
    }
    for (const view of cameraViews.values()) placeLabel(view.label, view.anchor);

    controls.update();
    renderer.render(scene, camera);
    requestAnimationFrame(frame);
  }

  setStatus("checking", mockMode ? "Starting mock" : "Connecting");
  setEmpty(true, "Connecting to the twin service.", "Nothing is shown until the twin service on this box answers.");
  requestAnimationFrame(frame);
  loadConfig();
  refreshFrames();
}

function liveSource() {
  return {
    mock: false,
    async get(path) {
      const response = await fetch(path, { cache: "no-store", signal: AbortSignal.timeout(2000) });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    },
    frameUrl(id) {
      return `${cameraFramePath(id)}?t=${Date.now()}`;
    },
  };
}
