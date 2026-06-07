import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const canvas = document.querySelector("#viewer");
const titleEl = document.querySelector("#viewer-title");
const subtitleEl = document.querySelector("#viewer-subtitle");
const statsEl = document.querySelector("#stats");
const modeSelect = document.querySelector("#mode-select");
const scaleInput = document.querySelector("#scale");
const animateButton = document.querySelector("#animate");
const readout = document.querySelector("#readout");

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearColor(0xeef2f5, 1);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000000);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;

const light = new THREE.DirectionalLight(0xffffff, 1.0);
light.position.set(1, 1.4, 1.2);
scene.add(light);
scene.add(new THREE.AmbientLight(0xffffff, 0.62));

let geometryPayload = null;
let modesManifest = null;
let activeMode = null;
let modelGroup = null;
let animating = false;
let animationStart = 0;

function resolveUrl(path) {
  return new URL(path, window.location.href).toString();
}

async function loadJson(path) {
  const response = await fetch(resolveUrl(path));
  if (!response.ok) {
    throw new Error(`${path}: ${response.status}`);
  }
  return response.json();
}

async function main() {
  const config = await loadJson("viewer_config.json");
  titleEl.textContent = config.title || "AVA FEM Viewer";
  geometryPayload = await loadJson(config.geometry_url);
  document.title = config.title || "AVA FEM Viewer";
  subtitleEl.textContent = `${geometryPayload.source.filename} | ${geometryPayload.source.parser}`;
  setStats(geometryPayload.stats);
  if (config.modes_url) {
    modesManifest = await loadJson(config.modes_url);
    setupModes(modesManifest);
  }
  rebuildModel();
  fitCamera();
  renderLoop();
}

function setStats(stats) {
  const items = [
    ["Nodes", stats.node_count],
    ["Elements", stats.element_count],
    ["Shells", stats.renderable_shell_count],
    ["Lines", stats.line_element_count],
    ["Masses", stats.mass_element_count],
  ];
  statsEl.innerHTML = items
    .map(([label, value]) => `<span class="stat">${label}: ${value ?? 0}</span>`)
    .join("");
}

function setupModes(manifest) {
  if (!manifest.modes || manifest.modes.length === 0) {
    return;
  }
  modeSelect.disabled = false;
  animateButton.disabled = false;
  for (const mode of manifest.modes) {
    const label = mode.frequency_hz == null
      ? `Mode ${mode.mode_number}`
      : `Mode ${mode.mode_number} | ${Number(mode.frequency_hz).toFixed(3)} Hz`;
    const option = document.createElement("option");
    option.value = mode.mode_id;
    option.textContent = label;
    modeSelect.appendChild(option);
  }
}

modeSelect.addEventListener("change", async () => {
  const modeId = modeSelect.value;
  activeMode = null;
  if (modeId && modesManifest) {
    const mode = modesManifest.modes.find((item) => item.mode_id === modeId);
    activeMode = await loadJson(`data/modes/${mode.shape_url}`);
  }
  rebuildModel();
  updateReadout();
});

scaleInput.addEventListener("input", () => {
  rebuildModel();
  updateReadout();
});

animateButton.addEventListener("click", () => {
  animating = !animating;
  animateButton.textContent = animating ? "Stop" : "Animate";
  animationStart = performance.now();
});

window.addEventListener("resize", resize);

function currentScale() {
  const span = Math.max(...geometryPayload.bounding_box.span, 1);
  const rawScale = Number(scaleInput.value) / 100;
  return rawScale * span;
}

function currentPhase() {
  if (!animating || !activeMode) {
    return 1;
  }
  return Math.sin((performance.now() - animationStart) / 260);
}

function modeMap(scale, phase) {
  const map = new Map();
  if (!activeMode) {
    return map;
  }
  const maxDisp = Math.max(
    ...activeMode.translations.map((row) => Math.hypot(row[0], row[1], row[2])),
    1e-16,
  );
  const normalizedScale = scale / maxDisp;
  activeMode.node_ids.forEach((nodeId, index) => {
    const row = activeMode.translations[index];
    map.set(Number(nodeId), new THREE.Vector3(
      row[0] * normalizedScale * phase,
      row[1] * normalizedScale * phase,
      row[2] * normalizedScale * phase,
    ));
  });
  return map;
}

function nodePosition(nodeById, nodeId, displacements) {
  const base = nodeById.get(Number(nodeId));
  if (!base) {
    return null;
  }
  const displacement = displacements.get(Number(nodeId));
  return displacement ? base.clone().add(displacement) : base.clone();
}

function rebuildModel() {
  if (!geometryPayload) {
    return;
  }
  if (modelGroup) {
    scene.remove(modelGroup);
  }
  modelGroup = new THREE.Group();
  scene.add(modelGroup);

  const nodeById = new Map(
    geometryPayload.nodes.map((node) => [Number(node.id), new THREE.Vector3(...node.xyz)]),
  );
  const displacements = modeMap(currentScale(), currentPhase());
  const shellPositions = [];
  const edgePositions = [];
  const pointPositions = [];

  for (const node of geometryPayload.nodes) {
    const point = nodePosition(nodeById, node.id, displacements);
    if (point) {
      pointPositions.push(point.x, point.y, point.z);
    }
  }

  for (const element of geometryPayload.elements) {
    const ids = element.node_ids.map(Number);
    for (const [a, b] of elementEdges(ids)) {
      const pa = nodePosition(nodeById, a, displacements);
      const pb = nodePosition(nodeById, b, displacements);
      if (pa && pb) {
        edgePositions.push(pa.x, pa.y, pa.z, pb.x, pb.y, pb.z);
      }
    }
    for (const tri of elementTriangles(element.type, ids)) {
      const points = tri.map((id) => nodePosition(nodeById, id, displacements));
      if (points.every(Boolean)) {
        for (const point of points) {
          shellPositions.push(point.x, point.y, point.z);
        }
      }
    }
  }

  if (shellPositions.length) {
    const shellGeometry = new THREE.BufferGeometry();
    shellGeometry.setAttribute("position", new THREE.Float32BufferAttribute(shellPositions, 3));
    shellGeometry.computeVertexNormals();
    const shellMaterial = new THREE.MeshPhongMaterial({
      color: 0x6ea8fe,
      opacity: 0.58,
      transparent: true,
      side: THREE.DoubleSide,
      shininess: 20,
    });
    modelGroup.add(new THREE.Mesh(shellGeometry, shellMaterial));
  }

  if (edgePositions.length) {
    const edgeGeometry = new THREE.BufferGeometry();
    edgeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(edgePositions, 3));
    modelGroup.add(new THREE.LineSegments(edgeGeometry, new THREE.LineBasicMaterial({ color: 0x1f3b57 })));
  }

  if (pointPositions.length) {
    const pointGeometry = new THREE.BufferGeometry();
    pointGeometry.setAttribute("position", new THREE.Float32BufferAttribute(pointPositions, 3));
    modelGroup.add(new THREE.Points(pointGeometry, new THREE.PointsMaterial({ color: 0x0b7285, size: 4, sizeAttenuation: false })));
  }
}

function elementTriangles(type, ids) {
  if (type.startsWith("CTRIA") && ids.length >= 3) {
    return [[ids[0], ids[1], ids[2]]];
  }
  if ((type.startsWith("CQUAD") || type === "CSHEAR") && ids.length >= 4) {
    return [[ids[0], ids[1], ids[2]], [ids[0], ids[2], ids[3]]];
  }
  return [];
}

function elementEdges(ids) {
  if (ids.length === 2) {
    return [[ids[0], ids[1]]];
  }
  if (ids.length === 3) {
    return [[ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[0]]];
  }
  if (ids.length === 4) {
    return [[ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[3]], [ids[3], ids[0]]];
  }
  if (ids.length >= 8) {
    return [
      [ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[3]], [ids[3], ids[0]],
      [ids[4], ids[5]], [ids[5], ids[6]], [ids[6], ids[7]], [ids[7], ids[4]],
      [ids[0], ids[4]], [ids[1], ids[5]], [ids[2], ids[6]], [ids[3], ids[7]],
    ];
  }
  return ids.slice(1).map((id, index) => [ids[index], id]);
}

function fitCamera() {
  const min = new THREE.Vector3(...geometryPayload.bounding_box.min);
  const max = new THREE.Vector3(...geometryPayload.bounding_box.max);
  const center = min.clone().add(max).multiplyScalar(0.5);
  const span = Math.max(...geometryPayload.bounding_box.span, 1);
  camera.position.copy(center).add(new THREE.Vector3(span * 1.2, -span * 1.5, span * 0.9));
  camera.near = span / 10000;
  camera.far = span * 10000;
  camera.updateProjectionMatrix();
  controls.target.copy(center);
  controls.update();
}

function updateReadout() {
  if (!activeMode) {
    readout.textContent = "";
    return;
  }
  const freq = activeMode.frequency_hz == null ? "frequency unavailable" : `${Number(activeMode.frequency_hz).toFixed(4)} Hz`;
  readout.textContent = `${activeMode.mode_id}: ${freq}, ${activeMode.node_ids.length} modal nodes`;
}

function resize() {
  const width = canvas.clientWidth || 1;
  const height = canvas.clientHeight || 1;
  if (canvas.width !== width || canvas.height !== height) {
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }
}

function renderLoop() {
  resize();
  if (animating && activeMode) {
    rebuildModel();
  }
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(renderLoop);
}

main().catch((error) => {
  subtitleEl.textContent = `Viewer error: ${error.message}`;
  console.error(error);
});
