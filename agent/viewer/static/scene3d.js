import * as THREE from "./vendor/three.module.min.js";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { parseSceneBuffer } from "./scene3d-format.js";

const REFRESH_MS = 2000;
const HAZARD_COLOR = new THREE.Color("#ff6a32");
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");

const elements = {
  canvas: document.querySelector("#scene3d-canvas"),
  stage: document.querySelector("#scene3d-stage"),
  state: document.querySelector("#scene3d-state"),
  empty: document.querySelector("#scene3d-empty"),
  depth: document.querySelector("#scene3d-depth"),
  orbitHint: document.querySelector("#scene3d-orbit-hint"),
};

let renderer;
let scene;
let camera;
let controls;
let pointGroup;
let resizeObserver;
let selectedEventId = null;
let requestInFlight = false;
let renderedOnce = false;

function setSceneState(kind, text) {
  elements.state.dataset.state = kind;
  elements.state.textContent = text;
}

function setEmpty(title, detail) {
  elements.empty.hidden = false;
  elements.empty.querySelector("p").textContent = title;
  elements.empty.querySelector("span").textContent = detail;
  elements.orbitHint.hidden = true;
}

function setupRenderer() {
  try {
    renderer = new THREE.WebGLRenderer({
      canvas: elements.canvas,
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
  } catch (_error) {
    setSceneState("offline", "WebGL unavailable");
    setEmpty("3D view unavailable.", "This browser could not start the local WebGL renderer.");
    return false;
  }

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  scene = new THREE.Scene();
  scene.background = new THREE.Color("#050709");
  scene.fog = new THREE.Fog("#050709", 3.2, 7.5);

  camera = new THREE.PerspectiveCamera(50, 1, 0.01, 50);
  camera.position.set(0, 0.35, 3.15);

  controls = new OrbitControls(camera, elements.canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.06;
  controls.enablePan = false;
  controls.minDistance = 1.15;
  controls.maxDistance = 6;
  controls.autoRotate = !REDUCED_MOTION.matches;
  controls.autoRotateSpeed = 0.42;

  const grid = new THREE.GridHelper(4, 16, "#3b4856", "#17202a");
  grid.position.y = -1.24;
  grid.material.transparent = true;
  grid.material.opacity = 0.38;
  scene.add(grid);

  resizeObserver = new ResizeObserver(resizeRenderer);
  resizeObserver.observe(elements.stage);
  resizeRenderer();
  animate();
  return true;
}

function resizeRenderer() {
  if (!renderer || !camera) return;
  const width = Math.max(1, elements.stage.clientWidth);
  const height = Math.max(1, elements.stage.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function animate() {
  window.requestAnimationFrame(animate);
  if (document.hidden || !renderer) return;
  controls.update();
  renderer.render(scene, camera);
}

function disposeGroup(group) {
  if (!group) return;
  group.traverse((child) => {
    child.geometry?.dispose();
    if (Array.isArray(child.material)) child.material.forEach((material) => material.dispose());
    else child.material?.dispose();
  });
  scene.remove(group);
}

function normalizePositions(positions) {
  if (positions.length === 0) return positions;
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let index = 0; index < positions.length; index += 3) {
    for (let axis = 0; axis < 3; axis += 1) {
      const value = positions[index + axis];
      min[axis] = Math.min(min[axis], value);
      max[axis] = Math.max(max[axis], value);
    }
  }
  const center = min.map((value, axis) => (value + max[axis]) / 2);
  const span = Math.max(max[0] - min[0], max[1] - min[1], max[2] - min[2], 0.0001);
  const scale = 2.45 / span;
  const normalized = new Float32Array(positions.length);
  for (let index = 0; index < positions.length; index += 3) {
    normalized[index] = (positions[index] - center[0]) * scale;
    normalized[index + 1] = (positions[index + 1] - center[1]) * scale;
    normalized[index + 2] = (positions[index + 2] - center[2]) * scale;
  }
  return normalized;
}

function buildCloud(sceneData) {
  const { header, colors, flags } = sceneData;
  const positions = normalizePositions(sceneData.positions);
  const normalPositions = [];
  const normalColors = [];
  const hazardPositions = [];

  for (let point = 0; point < header.count; point += 1) {
    const positionOffset = point * 3;
    const target = flags[point] === 1 ? hazardPositions : normalPositions;
    target.push(
      positions[positionOffset],
      positions[positionOffset + 1],
      positions[positionOffset + 2],
    );
    if (flags[point] !== 1) {
      normalColors.push(
        colors[positionOffset] / 255,
        colors[positionOffset + 1] / 255,
        colors[positionOffset + 2] / 255,
      );
    }
  }

  const group = new THREE.Group();
  if (normalPositions.length) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(normalPositions, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(normalColors, 3));
    const material = new THREE.PointsMaterial({
      size: 0.024,
      sizeAttenuation: true,
      vertexColors: true,
    });
    group.add(new THREE.Points(geometry, material));
  }
  if (hazardPositions.length) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(hazardPositions, 3));
    const material = new THREE.PointsMaterial({
      color: HAZARD_COLOR,
      size: 0.045,
      sizeAttenuation: true,
    });
    group.add(new THREE.Points(geometry, material));
  }
  return group;
}

function applyHorizontalFov(hfovDegrees) {
  if (!Number.isFinite(hfovDegrees) || hfovDegrees <= 1 || hfovDegrees >= 179) return;
  const horizontal = THREE.MathUtils.degToRad(hfovDegrees);
  const vertical = 2 * Math.atan(Math.tan(horizontal / 2) / camera.aspect);
  camera.fov = THREE.MathUtils.radToDeg(vertical);
  camera.updateProjectionMatrix();
}

function renderSceneBuffer(buffer) {
  const data = parseSceneBuffer(buffer);
  const replacement = buildCloud(data);
  disposeGroup(pointGroup);
  pointGroup = replacement;
  scene.add(pointGroup);
  applyHorizontalFov(Number(data.header.hfov_deg));
  controls.target.set(0, 0, 0);
  controls.update();

  elements.empty.hidden = true;
  elements.orbitHint.hidden = false;
  setSceneState("online", "Live depth");
  const depthMs = data.header.depth_ms;
  if (typeof depthMs === "number" && Number.isFinite(depthMs)) {
    elements.depth.textContent = `Measured on the GB10: ${depthMs} ms`;
    elements.depth.hidden = false;
  } else {
    elements.depth.hidden = true;
  }
  renderedOnce = true;
}

async function requestScene(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.arrayBuffer();
}

async function refreshScene() {
  if (requestInFlight || !renderer) return;
  requestInFlight = true;
  try {
    let buffer;
    try {
      buffer = await requestScene("/scene3d/scene/live");
    } catch (liveError) {
      if (!selectedEventId) throw liveError;
      buffer = await requestScene(`/scene3d/scene/event/${encodeURIComponent(selectedEventId)}`);
    }
    renderSceneBuffer(buffer);
  } catch (_error) {
    setSceneState("offline", "Scene unavailable");
    if (!renderedOnce) {
      setEmpty("3D depth unavailable.", "The local scene service is not reporting a frame yet.");
      elements.depth.hidden = true;
    }
  } finally {
    requestInFlight = false;
  }
}

window.addEventListener("ssw:event-selected", (event) => {
  selectedEventId = event.detail?.id || null;
});

REDUCED_MOTION.addEventListener("change", (event) => {
  if (controls) controls.autoRotate = !event.matches;
});

if (setupRenderer()) {
  refreshScene();
  window.setInterval(refreshScene, REFRESH_MS);
}
