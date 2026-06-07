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
const treeEl = document.querySelector("#model-tree");
const visibleCountEl = document.querySelector("#visible-count");

const DEFAULT_VIEW_DIRECTION = new THREE.Vector3(1.2, -1.5, 0.9).normalize();
const DEFAULT_DISPLAY_OPTIONS = {
  renderStyle: "shaded",
  colorMode: "property",
  elementOpacity: 65,
  showFloorGrid: true,
  showNodeMarkers: true,
  showElementEdges: true,
  showMassElements: true,
};

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
renderer.setClearColor(0xedf2f5, 1);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1000000);
camera.up.set(0, 0, 1);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.enablePan = true;
controls.enableZoom = true;
controls.screenSpacePanning = true;

const keyLight = new THREE.DirectionalLight(0xffffff, 1.0);
keyLight.position.set(1, 1.4, 1.2);
scene.add(keyLight);
scene.add(new THREE.AmbientLight(0xffffff, 0.62));

let geometryPayload = null;
let modesManifest = null;
let activeMode = null;
let modelGroup = null;
let modelTreeData = null;
let animating = false;
let animationStart = 0;

const expandedTreeSections = new Set(["render", "type", "property", "material"]);
let displayOptions = createDisplayOptions();

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
  modelTreeData = buildModelTreeData(geometryPayload);
  displayOptions = createDisplayOptions(modelTreeData);
  renderModelTree();
  if (config.modes_url) {
    modesManifest = await loadJson(config.modes_url);
    setupModes(modesManifest);
  }
  rebuildModel();
  fitCamera({ resetOrientation: true });
  renderLoop();
}

function createDisplayOptions(treeData = null) {
  return {
    ...DEFAULT_DISPLAY_OPTIONS,
    visibleElementTypes: new Set(treeData ? treeData.typeEntries.map((entry) => entry.key) : []),
    visiblePropertyIds: new Set(treeData ? treeData.propertyEntries.map((entry) => Number(entry.key)) : []),
    visibleMaterialIds: new Set(treeData ? treeData.materialEntries.map((entry) => Number(entry.key)) : []),
  };
}

function setStats(stats) {
  const items = [
    ["Nodes", stats.node_count],
    ["Elements", stats.element_count],
    ["Shells", stats.renderable_shell_count],
    ["Lines", stats.line_element_count],
    ["Solids", stats.solid_element_count],
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

treeEl.addEventListener("click", (event) => {
  const target = event.target;
  const groupHeader = target.closest("[data-tree-expand]");
  if (groupHeader) {
    const section = groupHeader.dataset.treeExpand;
    if (expandedTreeSections.has(section)) {
      expandedTreeSections.delete(section);
    } else {
      expandedTreeSections.add(section);
    }
    renderModelTree();
    return;
  }

  const actionButton = target.closest("[data-tree-action]");
  if (actionButton) {
    applyTreeBulkAction(actionButton.dataset.treeSection, actionButton.dataset.treeAction);
    rebuildModel();
    renderModelTree();
    return;
  }

  const commandButton = target.closest("[data-tree-command]");
  if (commandButton) {
    if (commandButton.dataset.treeCommand === "fit-model") {
      fitCamera();
    }
    if (commandButton.dataset.treeCommand === "reset-view") {
      fitCamera({ resetOrientation: true });
    }
  }
});

treeEl.addEventListener("change", (event) => {
  applyTreeControl(event.target);
});

treeEl.addEventListener("input", (event) => {
  applyTreeControl(event.target);
});

window.addEventListener("resize", resize);

function applyTreeBulkAction(section, action) {
  if (!modelTreeData) {
    return;
  }
  const useAll = action === "all";
  if (section === "type") {
    displayOptions.visibleElementTypes = new Set(useAll ? modelTreeData.typeEntries.map((entry) => entry.key) : []);
  }
  if (section === "property") {
    displayOptions.visiblePropertyIds = new Set(
      useAll ? modelTreeData.propertyEntries.map((entry) => Number(entry.key)) : [],
    );
  }
  if (section === "material") {
    displayOptions.visibleMaterialIds = new Set(
      useAll ? modelTreeData.materialEntries.map((entry) => Number(entry.key)) : [],
    );
  }
}

function applyTreeControl(target) {
  if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) {
    return;
  }

  if (target.dataset.treeSection && target.dataset.treeKey) {
    applyVisibilityCheckbox(target);
    rebuildModel();
    renderModelTree();
    return;
  }

  if (target.dataset.treeToggle) {
    const key = toggleKeyForControl(target.dataset.treeToggle);
    displayOptions[key] = target.checked;
    rebuildModel();
    renderModelTree();
    return;
  }

  if (target.dataset.treeSelect === "render-style") {
    displayOptions.renderStyle = target.value;
    rebuildModel();
    renderModelTree();
    return;
  }

  if (target.dataset.treeSelect === "color-mode") {
    displayOptions.colorMode = target.value;
    rebuildModel();
    renderModelTree();
    return;
  }

  if (target.dataset.treeRange === "element-opacity") {
    displayOptions.elementOpacity = Number(target.value);
    rebuildModel();
    renderModelTree();
  }
}

function applyVisibilityCheckbox(input) {
  const section = input.dataset.treeSection;
  const rawKey = input.dataset.treeKey;
  const key = section === "type" ? rawKey : Number(rawKey);
  const set = section === "type"
    ? displayOptions.visibleElementTypes
    : section === "property"
      ? displayOptions.visiblePropertyIds
      : displayOptions.visibleMaterialIds;
  if (input.checked) {
    set.add(key);
  } else {
    set.delete(key);
  }
}

function toggleKeyForControl(control) {
  return {
    "floor-grid": "showFloorGrid",
    "node-markers": "showNodeMarkers",
    "element-edges": "showElementEdges",
    "mass-elements": "showMassElements",
  }[control];
}

function buildModelTreeData(payload) {
  const elements = payload.elements || [];
  const masses = payload.mass_elements || [];
  const propertiesById = new Map((payload.properties || []).map((property) => [Number(property.id), property]));
  const materialsById = new Map((payload.materials || []).map((material) => [Number(material.id), material]));
  const typeCounts = new Map();
  const massTypeCounts = new Map();
  const propertyCounts = new Map();
  const materialCounts = new Map();

  for (const element of elements) {
    const type = String(element.type || "UNKNOWN");
    increment(typeCounts, type);
    if (element.property_id != null) {
      increment(propertyCounts, Number(element.property_id));
    }
    if (element.material_id != null) {
      increment(materialCounts, Number(element.material_id));
    }
  }

  for (const mass of masses) {
    const type = String(mass.type || "MASS");
    increment(typeCounts, type);
    increment(massTypeCounts, type);
  }

  const propertyIds = new Set([...propertiesById.keys(), ...propertyCounts.keys()]);
  const materialIds = new Set([...materialsById.keys(), ...materialCounts.keys()]);

  return {
    typeEntries: [...typeCounts.entries()]
      .sort(sortEntryKeys)
      .map(([key, count]) => ({
        key,
        label: key,
        count,
        detail: massTypeCounts.has(key) ? "Mass element" : "Structural element",
      })),
    propertyEntries: [...propertyIds]
      .sort((a, b) => a - b)
      .map((id) => {
        const property = propertiesById.get(id);
        const materials = property?.material_ids || [];
        return {
          key: String(id),
          label: `PID ${id}`,
          count: propertyCounts.get(id) || 0,
          detail: `${property?.type || "Property"}${materials.length ? ` | MAT ${materials.join(", ")}` : ""}`,
        };
      }),
    materialEntries: [...materialIds]
      .sort((a, b) => a - b)
      .map((id) => {
        const material = materialsById.get(id);
        const density = material?.density == null ? "" : ` | rho ${formatNumber(material.density)}`;
        return {
          key: String(id),
          label: `MAT ${id}`,
          count: materialCounts.get(id) || 0,
          detail: `${material?.type || "Material"}${density}`,
        };
      }),
  };
}

function increment(map, key) {
  map.set(key, (map.get(key) || 0) + 1);
}

function sortEntryKeys([a], [b]) {
  const an = Number(a);
  const bn = Number(b);
  if (Number.isFinite(an) && Number.isFinite(bn)) {
    return an - bn;
  }
  return String(a).localeCompare(String(b));
}

function renderModelTree() {
  if (!geometryPayload || !modelTreeData) {
    treeEl.innerHTML = `<p class="tree-empty">Load a BDF to populate the model tree.</p>`;
    return;
  }

  treeEl.innerHTML = [
    renderModelTreeGroup("render", "Viewer Controls", "View", renderViewerControls()),
    renderModelTreeSection("type", "Element Types", modelTreeData.typeEntries, displayOptions.visibleElementTypes),
    renderModelTreeSection("property", "Properties", modelTreeData.propertyEntries, displayOptions.visiblePropertyIds),
    renderModelTreeSection("material", "Materials", modelTreeData.materialEntries, displayOptions.visibleMaterialIds),
  ].join("");
}

function renderViewerControls() {
  return `
    <div class="tree-toolbar">
      <button class="tree-filter-chip" type="button" data-tree-command="fit-model">Fit Model</button>
      <button class="tree-filter-chip" type="button" data-tree-command="reset-view">Reset View</button>
    </div>
    <div class="tree-setting-row">
      <span class="tree-leaf-main">
        <span class="tree-leaf-label">Render Style</span>
        <span class="tree-leaf-meta">Shaded surfaces or wireframe edges</span>
      </span>
      <select class="select-input" data-tree-select="render-style">
        <option value="shaded" ${displayOptions.renderStyle === "shaded" ? "selected" : ""}>Shaded</option>
        <option value="wireframe" ${displayOptions.renderStyle === "wireframe" ? "selected" : ""}>Wireframe</option>
      </select>
    </div>
    <div class="tree-setting-row">
      <span class="tree-leaf-main">
        <span class="tree-leaf-label">Color By</span>
        <span class="tree-leaf-meta">Property or material identifiers</span>
      </span>
      <select class="select-input" data-tree-select="color-mode">
        <option value="property" ${displayOptions.colorMode === "property" ? "selected" : ""}>Property ID</option>
        <option value="material" ${displayOptions.colorMode === "material" ? "selected" : ""}>Material ID</option>
      </select>
    </div>
    <div class="tree-setting-row">
      <span class="tree-leaf-main">
        <span class="tree-leaf-label">Element Opacity</span>
        <span class="tree-leaf-meta">Structural surface transparency</span>
      </span>
      <span class="tree-range-control">
        <input
          class="range-input"
          type="range"
          min="5"
          max="100"
          step="1"
          value="${displayOptions.elementOpacity}"
          data-tree-range="element-opacity"
        />
        <span class="tree-badge">${displayOptions.elementOpacity}%</span>
      </span>
    </div>
    <div class="tree-leaf-list">
      ${renderToggle("floor-grid", "Floor Grid", "XY reference grid", "Grid", displayOptions.showFloorGrid)}
      ${renderToggle("node-markers", "Node Markers", "GRID points attached to visible topology", "GRID", displayOptions.showNodeMarkers)}
      ${renderToggle("element-edges", "Element Edges", "Shell, line, and solid outlines", "Edge", displayOptions.showElementEdges)}
      ${renderToggle("mass-elements", "Mass Glyphs", "CONM and scalar mass markers", "Mass", displayOptions.showMassElements)}
    </div>
  `;
}

function renderToggle(key, label, detail, badge, checked) {
  return `
    <label class="tree-leaf">
      <input type="checkbox" data-tree-toggle="${key}" ${checked ? "checked" : ""} />
      <span class="tree-leaf-main">
        <span class="tree-leaf-label">${escapeHtml(label)}</span>
        <span class="tree-leaf-meta">${escapeHtml(detail)}</span>
      </span>
      <span class="tree-badge">${escapeHtml(badge)}</span>
    </label>
  `;
}

function renderModelTreeSection(section, title, entries, visibleKeys) {
  const body = entries.length
    ? `
      <div class="tree-toolbar">
        <button class="tree-filter-chip" type="button" data-tree-action="all" data-tree-section="${section}">All</button>
        <button class="tree-filter-chip" type="button" data-tree-action="none" data-tree-section="${section}">None</button>
      </div>
      <div class="tree-leaf-list">
        ${entries.map((entry) => renderModelTreeEntry(section, entry, visibleKeys)).join("")}
      </div>
    `
    : `<p class="tree-empty">No ${escapeHtml(title.toLowerCase())} found.</p>`;
  return renderModelTreeGroup(section, title, entries.length, body);
}

function renderModelTreeGroup(section, title, badge, body) {
  const isExpanded = expandedTreeSections.has(section);
  return `
    <section class="tree-group">
      <button
        class="tree-group-header"
        type="button"
        data-tree-expand="${escapeAttr(section)}"
        aria-expanded="${isExpanded ? "true" : "false"}"
      >
        <span class="tree-caret${isExpanded ? " open" : ""}"></span>
        <span class="tree-label">${escapeHtml(title)}</span>
        <span class="tree-badge">${escapeHtml(String(badge))}</span>
      </button>
      <div class="tree-group-body${isExpanded ? "" : " tree-group-body-hidden"}">
        ${body}
      </div>
    </section>
  `;
}

function renderModelTreeEntry(section, entry, visibleKeys) {
  const key = section === "type" ? entry.key : Number(entry.key);
  const checked = visibleKeys.has(key);
  return `
    <label class="tree-leaf">
      <input
        type="checkbox"
        data-tree-section="${escapeAttr(section)}"
        data-tree-key="${escapeAttr(entry.key)}"
        ${checked ? "checked" : ""}
      />
      <span class="tree-leaf-main">
        <span class="tree-leaf-label">${escapeHtml(entry.label)}</span>
        <span class="tree-leaf-meta">${escapeHtml(entry.detail)}</span>
      </span>
      <span class="tree-badge">${Number(entry.count).toLocaleString()}</span>
    </label>
  `;
}

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
    if (!row) {
      return;
    }
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
    disposeObject(modelGroup);
  }
  modelGroup = new THREE.Group();
  scene.add(modelGroup);

  const nodeById = new Map(
    geometryPayload.nodes.map((node) => [Number(node.id), new THREE.Vector3(...node.xyz)]),
  );
  const displacements = modeMap(currentScale(), currentPhase());
  const visibleElements = [];
  const visibleMasses = [];
  const visibleNodeIds = new Set();
  const shellPositions = [];
  const shellColors = [];
  const linePositions = [];
  const lineColors = [];
  const pointPositions = [];

  for (const element of geometryPayload.elements || []) {
    if (!isElementVisible(element)) {
      continue;
    }
    visibleElements.push(element);
    const ids = (element.node_ids || []).map(Number);
    ids.forEach((id) => visibleNodeIds.add(id));
    const color = colorForElement(element);
    const edgeColor = color.clone().lerp(new THREE.Color(0x17202a), 0.35);

    if (displayOptions.showElementEdges || displayOptions.renderStyle === "wireframe") {
      addElementEdges(element.type, ids, nodeById, displacements, linePositions, lineColors, edgeColor);
    }

    if (displayOptions.renderStyle === "shaded") {
      addShellTriangles(element, ids, nodeById, displacements, shellPositions, shellColors, color);
    }
  }

  for (const mass of geometryPayload.mass_elements || []) {
    if (!isMassVisible(mass)) {
      continue;
    }
    const center = nodePosition(nodeById, mass.node_id, displacements);
    if (!center) {
      continue;
    }
    visibleMasses.push(mass);
    visibleNodeIds.add(Number(mass.node_id));
    const color = colorForType(mass.type || "MASS").lerp(new THREE.Color(0x592f67), 0.35);
    addMassGlyph(center, glyphSize(), linePositions, lineColors, color);
  }

  if (displayOptions.showNodeMarkers) {
    for (const nodeId of visibleNodeIds) {
      const point = nodePosition(nodeById, nodeId, displacements);
      if (point) {
        pointPositions.push(point.x, point.y, point.z);
      }
    }
  }

  if (displayOptions.showFloorGrid) {
    addFloorGrid();
  }
  addShellMesh(shellPositions, shellColors);
  addLineSegments(linePositions, lineColors);
  addNodePoints(pointPositions);
  updateVisibleCount(visibleElements.length, visibleMasses.length);
}

function isElementVisible(element) {
  const type = String(element.type || "UNKNOWN");
  if (!displayOptions.visibleElementTypes.has(type)) {
    return false;
  }
  if (element.property_id != null && modelTreeData.propertyEntries.length > 0) {
    if (!displayOptions.visiblePropertyIds.has(Number(element.property_id))) {
      return false;
    }
  }
  if (element.material_id != null && modelTreeData.materialEntries.length > 0) {
    if (!displayOptions.visibleMaterialIds.has(Number(element.material_id))) {
      return false;
    }
  }
  return element.renderable !== false;
}

function isMassVisible(mass) {
  return displayOptions.showMassElements && displayOptions.visibleElementTypes.has(String(mass.type || "MASS"));
}

function addShellTriangles(element, ids, nodeById, displacements, positions, colors, color) {
  for (const tri of elementTriangles(element.type, ids)) {
    const points = tri.map((id) => nodePosition(nodeById, id, displacements));
    if (!points.every(Boolean)) {
      continue;
    }
    for (const point of points) {
      positions.push(point.x, point.y, point.z);
      colors.push(color.r, color.g, color.b);
    }
  }
}

function addElementEdges(type, ids, nodeById, displacements, positions, colors, color) {
  for (const [a, b] of elementEdges(type, ids)) {
    const pa = nodePosition(nodeById, a, displacements);
    const pb = nodePosition(nodeById, b, displacements);
    if (!pa || !pb) {
      continue;
    }
    positions.push(pa.x, pa.y, pa.z, pb.x, pb.y, pb.z);
    colors.push(color.r, color.g, color.b, color.r, color.g, color.b);
  }
}

function addMassGlyph(center, size, positions, colors, color) {
  const corners = [
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
    [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
  ].map(([x, y, z]) => new THREE.Vector3(
    center.x + x * size,
    center.y + y * size,
    center.z + z * size,
  ));
  const segments = [
    [0, 1], [1, 2], [2, 3], [3, 0],
    [4, 5], [5, 6], [6, 7], [7, 4],
    [0, 4], [1, 5], [2, 6], [3, 7],
    [0, 6], [1, 7], [2, 4], [3, 5],
  ];
  for (const [a, b] of segments) {
    const pa = corners[a];
    const pb = corners[b];
    positions.push(pa.x, pa.y, pa.z, pb.x, pb.y, pb.z);
    colors.push(color.r, color.g, color.b, color.r, color.g, color.b);
  }
}

function addFloorGrid() {
  const span = modelSpan();
  const size = Math.max(span * 1.35, 1);
  const divisions = 12;
  const grid = new THREE.GridHelper(size, divisions, 0x9fb0bc, 0xd4dde4);
  grid.rotation.x = Math.PI / 2;
  grid.position.z = Number(geometryPayload.bounding_box.min?.[2] || 0);
  modelGroup.add(grid);
}

function addShellMesh(positions, colors) {
  if (!positions.length) {
    return;
  }
  const shellGeometry = new THREE.BufferGeometry();
  shellGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  shellGeometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  shellGeometry.computeVertexNormals();
  const opacity = displayOptions.elementOpacity / 100;
  const shellMaterial = new THREE.MeshPhongMaterial({
    vertexColors: true,
    opacity,
    transparent: opacity < 1,
    side: THREE.DoubleSide,
    shininess: 20,
  });
  modelGroup.add(new THREE.Mesh(shellGeometry, shellMaterial));
}

function addLineSegments(positions, colors) {
  if (!positions.length) {
    return;
  }
  const lineGeometry = new THREE.BufferGeometry();
  lineGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  lineGeometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  modelGroup.add(new THREE.LineSegments(
    lineGeometry,
    new THREE.LineBasicMaterial({ vertexColors: true }),
  ));
}

function addNodePoints(positions) {
  if (!positions.length) {
    return;
  }
  const pointGeometry = new THREE.BufferGeometry();
  pointGeometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  modelGroup.add(new THREE.Points(
    pointGeometry,
    new THREE.PointsMaterial({ color: 0x0b7285, size: 4, sizeAttenuation: false }),
  ));
}

function updateVisibleCount(elementCount, massCount) {
  if (!visibleCountEl) {
    return;
  }
  const totalElements = (geometryPayload.elements || []).length;
  const totalMasses = (geometryPayload.mass_elements || []).length;
  visibleCountEl.textContent = `${elementCount}/${totalElements} elements | ${massCount}/${totalMasses} masses`;
}

function elementTriangles(type, ids) {
  if (String(type).startsWith("CTRIA") && ids.length >= 3) {
    return [[ids[0], ids[1], ids[2]]];
  }
  if ((String(type).startsWith("CQUAD") || type === "CSHEAR") && ids.length >= 4) {
    return [[ids[0], ids[1], ids[2]], [ids[0], ids[2], ids[3]]];
  }
  return [];
}

function elementEdges(type, ids) {
  const elementType = String(type || "");
  if (ids.length === 2) {
    return [[ids[0], ids[1]]];
  }
  if (elementType.startsWith("CTRIA") && ids.length >= 3) {
    return [[ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[0]]];
  }
  if ((elementType.startsWith("CQUAD") || elementType === "CSHEAR") && ids.length >= 4) {
    return [[ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[3]], [ids[3], ids[0]]];
  }
  if (elementType === "CTETRA" && ids.length >= 4) {
    return [[ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[0]], [ids[0], ids[3]], [ids[1], ids[3]], [ids[2], ids[3]]];
  }
  if (elementType === "CPENTA" && ids.length >= 6) {
    return [
      [ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[0]],
      [ids[3], ids[4]], [ids[4], ids[5]], [ids[5], ids[3]],
      [ids[0], ids[3]], [ids[1], ids[4]], [ids[2], ids[5]],
    ];
  }
  if (elementType === "CPYRAM" && ids.length >= 5) {
    return [
      [ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[3]], [ids[3], ids[0]],
      [ids[0], ids[4]], [ids[1], ids[4]], [ids[2], ids[4]], [ids[3], ids[4]],
    ];
  }
  if (elementType === "CHEXA" && ids.length >= 8) {
    return [
      [ids[0], ids[1]], [ids[1], ids[2]], [ids[2], ids[3]], [ids[3], ids[0]],
      [ids[4], ids[5]], [ids[5], ids[6]], [ids[6], ids[7]], [ids[7], ids[4]],
      [ids[0], ids[4]], [ids[1], ids[5]], [ids[2], ids[6]], [ids[3], ids[7]],
    ];
  }
  if (ids.length >= 3) {
    return ids.slice(1).map((id, index) => [ids[index], id]);
  }
  return [];
}

function colorForElement(element) {
  if (displayOptions.colorMode === "material" && element.material_id != null) {
    return colorFromId(Number(element.material_id), 0.6, 0.48);
  }
  if (displayOptions.colorMode === "property" && element.property_id != null) {
    return colorFromId(Number(element.property_id), 0.58, 0.5);
  }
  return colorForType(element.type || "UNKNOWN");
}

function colorForType(type) {
  let hash = 0;
  for (const char of String(type)) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return colorFromId(hash || 1, 0.52, 0.52);
}

function colorFromId(id, saturation, lightness) {
  const hue = ((Number(id) * 137.508) % 360) / 360;
  return new THREE.Color().setHSL(hue, saturation, lightness);
}

function glyphSize() {
  return Math.max(modelSpan() * 0.012, 0.02);
}

function modelSpan() {
  return Math.max(...(geometryPayload.bounding_box.span || [1, 1, 1]), 1);
}

function fitCamera({ resetOrientation = false } = {}) {
  if (!geometryPayload) {
    return;
  }
  resize();
  const min = new THREE.Vector3(...geometryPayload.bounding_box.min);
  const max = new THREE.Vector3(...geometryPayload.bounding_box.max);
  const center = min.clone().add(max).multiplyScalar(0.5);
  const span = Math.max(...geometryPayload.bounding_box.span, 1);
  const radius = Math.max(min.distanceTo(max) * 0.5, span * 0.5, 1);
  const fov = THREE.MathUtils.degToRad(camera.fov);
  const distance = Math.max((radius / Math.sin(fov / 2)) * 1.15, radius * 2);
  const currentDirection = camera.position.clone().sub(controls.target).normalize();
  const direction = resetOrientation || currentDirection.lengthSq() === 0
    ? DEFAULT_VIEW_DIRECTION
    : currentDirection;
  camera.position.copy(center).add(direction.clone().multiplyScalar(distance));
  camera.near = Math.max(distance / 10000, 0.001);
  camera.far = Math.max(distance * 10000, 1000);
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

function disposeObject(object) {
  object.traverse((child) => {
    if (child.geometry) {
      child.geometry.dispose();
    }
    if (Array.isArray(child.material)) {
      child.material.forEach((material) => material.dispose());
    } else if (child.material) {
      child.material.dispose();
    }
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

function formatNumber(value) {
  if (!Number.isFinite(Number(value))) {
    return String(value);
  }
  return Number(value).toLocaleString(undefined, { maximumSignificantDigits: 4 });
}

main().catch((error) => {
  subtitleEl.textContent = `Viewer error: ${error.message}`;
  treeEl.innerHTML = `<p class="tree-empty">Viewer error: ${escapeHtml(error.message)}</p>`;
  console.error(error);
});
