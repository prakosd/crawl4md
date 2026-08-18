// Standalone 3D "crawl universe" scene. Inlined into the self-contained page the
// launcher opens in a new tab; three.js loads from the pinned CDN via the import
// map in viewer.html. Reads the crawl model from window.__SITE_GRAPH__ and the
// localized labels from window.__VIEWER_LABELS__.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";

// ── Data + labels ────────────────────────────────────────────────────────────
const MODEL = window.__SITE_GRAPH__ || { nodes: [], edges: [], root_ids: [], stats: {} };
const L = window.__VIEWER_LABELS__ || {};
const t = (key, fallback) => (L[key] != null ? L[key] : fallback != null ? fallback : key);

// ── Tuning constants ─────────────────────────────────────────────────────────
const MIN_PLANET_R = 0.6;
const MAX_PLANET_R = 3.0;
const SUN_R = 3.4;
const SUN_CLEARANCE = 9; // min camera clearance from the central sun
const ROOT_CLUSTER_R = 3.0; // radius when several seed pages share the centre
const ORBIT_BASE_SPEED = 0.16;
const AUTO_ROTATE_SPEED = 0.2; // idle camera auto-revolve speed (OrbitControls units)
// Nested clusters: each page's children orbit that page. The local ring grows with
// the brood size and the sqrt of the subtree weight, so a busy page flings its
// children out into their own separated cluster (galaxy-of-clusters look).
const LOCAL_RING_MIN = 6.0; // closest a child sits to its parent
const LOCAL_RING_PER_DESC = 4.2; // fling a child out by sqrt(its own subtree size)
const LOCAL_WEDGE_MIN = 1.0; // min angular share for a leaf child
const LOCAL_ANGLE_JITTER = 0.35; // radians of angular wobble per child
const LOCAL_RADIAL_JITTER = 1.6; // world-unit spread across a local ring band
const LOCAL_VERTICAL_JITTER = 2.4; // small vertical scatter within a cluster
const SEG_PER_EDGE = 18; // samples per curved link (trajectory-arc smoothness)
const STAR_COUNT = 1600;
const HOVER_MS = 33;
const CLICK_DRAG_PX = 6;
const KEY_PAN_SPEED = 0.9;
const PREVIEW_TIMEOUT_MS = 6000;

const STATUS_CSS = {
  success: "#57d38c",
  fail: "#ff6b6b",
  skipped: "#9aa6be",
  discovered: "#6f7ba0",
};
const PALETTE = {
  success: { base: "#1f4e70", land: "#3fbf82", cap: "#eaf3ff" },
  fail: { base: "#6e3320", land: "#c05a34", cap: "#f0d3bd" },
  skipped: { base: "#454b56", land: "#6b7280", cap: "#d2d8e2" },
  discovered: { base: "#33406a", land: "#5566a0", cap: "#c2cbe8" },
};
// Successful pages vary across biomes (picked by URL hash) so the galaxy reads
// colourful, not all-green; richness still drives how detailed the surface is.
const SUCCESS_BIOMES = [
  { base: "#173a5e", land: "#3fa7d6", cap: "#eaf6ff" }, // ocean blue
  { base: "#1f5040", land: "#43c17a", cap: "#e8fff0" }, // earth green
  { base: "#164a52", land: "#38c6c2", cap: "#e3fbfa" }, // teal
  { base: "#5a4326", land: "#d0a24c", cap: "#fff2d6" }, // desert tan
  { base: "#3a2350", land: "#9a6cd6", cap: "#f2e6ff" }, // violet
  { base: "#334a66", land: "#8fbce6", cap: "#f0f6ff" }, // ice cyan
];
// Gas giants (the biggest pages) read as Saturn: cream/tan bands + a ringed disc.
const SATURN_PAL = { base: "#6b5a3c", land: "#cbb583", cap: "#efe3c4" };
// Real NASA textures per body type, swapped in over the procedural look when the
// CDN is reachable. SUCCESS_BIOME_TEX indexes align with SUCCESS_BIOMES.
const SUCCESS_BIOME_TEX = [
  "earth.jpg",
  "neptune.jpg",
  "uranus.jpg",
  "venus.jpg",
  "mars.jpg",
  "jupiter.jpg",
];
const CATEGORY_TEX = { skipped: "mercury.jpg", discovered: "mercury.jpg" };
const GIANT_TEX = "saturn.jpg";
const RETRY_EMISSIVE = 0xffce54;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const canvas = document.getElementById("sg-canvas");
const tooltipEl = document.getElementById("sg-tooltip");
const infoEl = document.getElementById("sg-info");
const infoTitle = document.getElementById("sg-info-title");
const infoFields = document.getElementById("sg-info-fields");
const openPageEl = document.getElementById("sg-open-page");
const previewEl = document.getElementById("sg-preview");
const previewMsg = document.getElementById("sg-preview-msg");

document.title = t("title", "Site Orrery");
document.getElementById("sg-title").textContent = t("title", "Site Orrery");
document.getElementById("sg-help-label").textContent = t("controls_title", "Controls");
document.getElementById("sg-info-close").setAttribute("aria-label", t("panel_close", "Close"));

// ── Renderer, scene, camera ──────────────────────────────────────────────────
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x05070d, 0.0016);

const camera = new THREE.PerspectiveCamera(
  55,
  window.innerWidth / window.innerHeight,
  0.1,
  6000,
);

const systemGroup = new THREE.Group();
scene.add(systemGroup);

// Warm ambient + hemisphere fill keep night sides dim (not black); the sun's
// point light has NO distance decay (4th arg 0) so every planet — even the
// outermost ring — catches its light, giving a real day/night terminator.
scene.add(new THREE.AmbientLight(0xb8c4e0, 0.32));
scene.add(new THREE.HemisphereLight(0x9fb4ff, 0x140f22, 0.35));
const centralLight = new THREE.PointLight(0xfff1d4, 3.0, 0, 0);
systemGroup.add(centralLight);

// ── Post-processing (bloom makes the suns glow) ──────────────────────────────
const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const bloomPass = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight),
  1.15, // strength
  0.55, // radius
  0.62, // threshold — only bright emissive suns bloom
);
composer.addPass(bloomPass);

// ── Controls ─────────────────────────────────────────────────────────────────
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.rotateSpeed = 0.7;
controls.panSpeed = 0.8;
controls.minDistance = 6;
controls.autoRotateSpeed = AUTO_ROTATE_SPEED;

// ── Realistic textures (CDN, procedural/black fallback) ──────────────────
const TEX_BASE = window.__TEXTURE_BASE__ || "";
const texLoader = new THREE.TextureLoader();
texLoader.setCrossOrigin("anonymous");
const cdnTexCache = new Map(); // file -> { tex, waiters[] }

function loadCdnTexture(file, onLoad) {
  if (!TEX_BASE) return;
  let entry = cdnTexCache.get(file);
  if (entry) {
    if (entry.tex) onLoad(entry.tex);
    else entry.waiters.push(onLoad);
    return;
  }
  entry = { tex: null, waiters: [onLoad] };
  cdnTexCache.set(file, entry);
  texLoader.load(
    `${TEX_BASE}/${file}`,
    (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
      entry.tex = tex;
      entry.waiters.forEach((w) => w(tex));
      entry.waiters = [];
    },
    undefined,
    () => {}, // keep the procedural / black fallback on error
  );
}

function applyCdnTexture(material, file) {
  if (!file) return;
  loadCdnTexture(file, (tex) => {
    material.map = tex;
    material.needsUpdate = true;
  });
}

// Milky Way backdrop: a real equirectangular star map when reachable, else the
// dark base colour (the faint Points starfield still shows either way). Using the
// 8K map for fidelity (heavier GPU memory, ~128 MB); swap to "stars.jpg" (2K,
// ~8 MB) if targeting low-end GPUs.
scene.background = new THREE.Color(0x05070d);
loadCdnTexture("8k_stars.jpg", (tex) => {
  tex.mapping = THREE.EquirectangularReflectionMapping;
  scene.background = tex;
});

// ── Focus + idle auto-rotate ──────────────────────────────────
const _focusPos = new THREE.Vector3();
const IDLE_MS = 10000;
const IDLE_RAMP_LAMBDA = 1.5; // exponential ease rate for ambient motion in/out
// Start "idle" (timer set in the past) so ambient motion eases in gently on load
// and only pauses once the user interacts.
let lastInteract = performance.now() - IDLE_MS;
let idleFactor = 0; // 0 = interacting (still), 1 = fully idle (ambient motion)
let focusMesh = null;
let focusHalo = null;
let followFocus = false; // camera tracks the focused planet until the user pans
let focusChain = null; // Set<edgeIndex> from the focused planet up to the root
let focusOrder = null; // Map<edgeIndex, position> root(0)->planet for the flow
let focusLen = 0;
let hoverChain = null; // Set<edgeIndex> highlighted while hovering
let linksDirty = false; // repaint link colours once when hover/focus changes

function markInteract() {
  lastInteract = performance.now();
}

// Click focus: re-centre the orbit pivot on a planet, mark it with a cyan halo,
// and light its trajectory chain up to the root.
function setFocus(mesh) {
  if (focusHalo && focusHalo.parent) focusHalo.parent.remove(focusHalo);
  focusHalo = null;
  focusChain = null;
  focusOrder = null;
  focusLen = 0;
  followFocus = false;
  linksDirty = true;
  focusMesh = mesh || null;
  if (!focusMesh) return;
  followFocus = true;
  const ordered = orderedChain(focusMesh.userData.node.id);
  if (ordered.length) {
    focusChain = new Set(ordered);
    focusOrder = new Map(ordered.map((edge, k) => [edge, k]));
    focusLen = ordered.length;
  }
  const r = (focusMesh.geometry.parameters && focusMesh.geometry.parameters.radius) || 1;
  focusHalo = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: GLOW_TEXTURE,
      color: 0x7fdfff,
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
      opacity: 0.85,
    }),
  );
  focusHalo.scale.setScalar(r * 4.2);
  focusMesh.add(focusHalo);
}

controls.addEventListener("start", markInteract);
renderer.domElement.addEventListener("wheel", markInteract, { passive: true });

// ── Starfield background ─────────────────────────────────────────────────────
function addStarfield() {
  const positions = new Float32Array(STAR_COUNT * 3);
  for (let i = 0; i < STAR_COUNT; i++) {
    const r = 900 + Math.random() * 2600;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = r * Math.cos(phi);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const mat = new THREE.PointsMaterial({
    color: 0xbcd0ff,
    size: 2.1,
    sizeAttenuation: true,
    transparent: true,
    opacity: 0.85,
    depthWrite: false,
    fog: false,
  });
  const stars = new THREE.Points(geo, mat);
  scene.add(stars);
  return stars;
}
const starfield = addStarfield();

// (Procedural galaxy removed — a real equirectangular star map now loads from
// the CDN into scene.background near the top, with a dark fallback.)

// ── Deterministic PRNG (stable procedural textures) ──────────────────────────
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let x = Math.imul(a ^ (a >>> 15), 1 | a);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

// ── Procedural planet textures (shared per look bucket) ──────────────────────
const textureCache = new Map();
function planetTexture(palKey, pal, richnessBucket, isGiant) {
  const key = `${palKey}|${richnessBucket}|${isGiant ? "g" : "p"}`;
  const cached = textureCache.get(key);
  if (cached) return cached;

  const w = 512;
  const h = 256;
  const cv = document.createElement("canvas");
  cv.width = w;
  cv.height = h;
  const ctx = cv.getContext("2d");
  const rand = mulberry32(hashString(key));

  ctx.fillStyle = pal.base;
  ctx.fillRect(0, 0, w, h);

  if (isGiant) {
    // Gas-giant horizontal bands in the category hue.
    const bands = 9 + richnessBucket * 3;
    for (let i = 0; i < bands; i++) {
      const y = (i / bands) * h;
      const bh = h / bands;
      const shade = 0.7 + rand() * 0.6;
      ctx.fillStyle = shadeColor(pal.land, shade);
      ctx.globalAlpha = 0.35 + rand() * 0.3;
      ctx.fillRect(0, y, w, bh);
    }
    ctx.globalAlpha = 1;
  } else {
    // Rocky/earthy world: land blobs + polar caps grow with richness so a rich
    // page reads as a lush planet and a bare one as a barren rock.
    const blobs = 6 + richnessBucket * 22;
    for (let i = 0; i < blobs; i++) {
      const x = rand() * w;
      const y = h * (0.18 + rand() * 0.64);
      const rr = 6 + rand() * (12 + richnessBucket * 10);
      ctx.fillStyle = shadeColor(pal.land, 0.8 + rand() * 0.5);
      ctx.globalAlpha = 0.55 + rand() * 0.35;
      ctx.beginPath();
      ctx.ellipse(x, y, rr, rr * (0.6 + rand() * 0.5), rand() * Math.PI, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    const cap = 8 + richnessBucket * 7;
    ctx.fillStyle = pal.cap;
    ctx.globalAlpha = 0.5 + richnessBucket * 0.12;
    ctx.fillRect(0, 0, w, cap);
    ctx.fillRect(0, h - cap, w, cap);
    ctx.globalAlpha = 1;
  }

  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
  textureCache.set(key, tex);
  return tex;
}

function hashString(str) {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function shadeColor(hex, factor) {
  const c = new THREE.Color(hex);
  c.multiplyScalar(factor);
  c.r = Math.min(c.r, 1);
  c.g = Math.min(c.g, 1);
  c.b = Math.min(c.b, 1);
  return `#${c.getHexString()}`;
}

// ── Layout: orbital rings by crawl depth ─────────────────────────────────────
const nodes = Array.isArray(MODEL.nodes) ? MODEL.nodes : [];
const nodeById = new Map(nodes.map((n) => [n.id, n]));
const planetById = new Map();
const planets = []; // { node, mesh, pivot, selfSpeed }

function planetRadius(node) {
  const s = clamp01(Number(node.size_scale) || 0);
  return MIN_PLANET_R + s * (MAX_PLANET_R - MIN_PLANET_R);
}
function clamp01(v) {
  return Math.max(0, Math.min(1, v));
}

function cmp(a, b) {
  return a < b ? -1 : a > b ? 1 : 0;
}

function ringSpeed(radius) {
  return radius > 0 ? ORBIT_BASE_SPEED / Math.sqrt(radius) : 0;
}

// Nested orbital layout: each page's children orbit that page, so the crawl reads
// as a galaxy of clusters (moons around planets around the sun) rather than flat
// depth rings. A page's local ring scales with its subtree, flinging busy pages'
// broods out into their own separated cluster.
function buildLayout() {
  const childrenById = new Map();
  for (const node of nodes) {
    const parent = node.parent;
    if (parent != null && nodeById.has(parent) && parent !== node.id) {
      if (!childrenById.has(parent)) childrenById.set(parent, []);
      childrenById.get(parent).push(node);
    }
  }
  let outer = SUN_CLEARANCE;

  // Place a page's not-yet-placed children on a local ring around it, parenting
  // their orbits to the page's own system so they revolve with it.
  function layoutChildren(node, nodeSystem) {
    const kids = (childrenById.get(node.id) || []).filter((k) => !planetById.has(k.id));
    if (kids.length === 0) return;
    kids.sort((a, b) => cmp(a.id, b.id));
    // Angular wedge per child scales with its subtree, so a busy child claims more
    // arc; its orbit radius scales with its subtree too, flinging its cluster out
    // clear of the parent and its siblings.
    const weight = (k) => LOCAL_WEDGE_MIN + Math.sqrt(Number(k.descendant_count) || 0);
    const total = kids.reduce((s, k) => s + weight(k), 0);
    let acc = 0;
    kids.forEach((child) => {
      const rng = mulberry32(hashString(child.id));
      const w = weight(child);
      const angle = ((acc + w / 2) / total) * Math.PI * 2 + (rng() - 0.5) * LOCAL_ANGLE_JITTER;
      acc += w;
      const desc = Number(child.descendant_count) || 0;
      const radius =
        LOCAL_RING_MIN +
        LOCAL_RING_PER_DESC * Math.sqrt(desc) +
        (rng() - 0.5) * 2 * LOCAL_RADIAL_JITTER;
      const y = (rng() - 0.5) * 2 * LOCAL_VERTICAL_JITTER;
      const childSystem = createBody(child, {
        radius,
        angle,
        y,
        orbitSpeed: ringSpeed(radius),
        isRoot: false,
        parentSystem: nodeSystem,
      });
      layoutChildren(child, childSystem);
    });
  }

  const roots = nodes.filter((n) => n.is_root || !nodeById.has(n.parent));
  roots.sort((a, b) => cmp(a.id, b.id));
  roots.forEach((node, i) => {
    const angle = roots.length > 1 ? (i / roots.length) * Math.PI * 2 : 0;
    const radius = roots.length > 1 ? ROOT_CLUSTER_R : 0;
    const rootSystem = createBody(node, {
      radius,
      angle,
      y: 0,
      orbitSpeed: 0,
      isRoot: true,
      parentSystem: systemGroup,
    });
    layoutChildren(node, rootSystem);
  });

  // Safety net: place any node unreachable from a root (e.g. a discovered-from
  // cycle) at the centre so nothing silently disappears.
  for (const node of nodes) {
    if (planetById.has(node.id)) continue;
    const sys = createBody(node, {
      radius: 0,
      angle: 0,
      y: 0,
      orbitSpeed: 0,
      isRoot: false,
      parentSystem: systemGroup,
    });
    layoutChildren(node, sys);
  }

  // Frame the camera to the actual built extent (max node distance from centre),
  // not the worst-case radius sum, so the clusters fill the view at any depth.
  systemGroup.updateMatrixWorld(true);
  const worldPos = new THREE.Vector3();
  for (const p of planets) {
    p.mesh.getWorldPosition(worldPos);
    outer = Math.max(outer, worldPos.length());
  }
  return outer;
}

function createBody(node, { radius, angle, y, orbitSpeed, isRoot, parentSystem }) {
  const orbit = new THREE.Group();
  const pivot = new THREE.Group();
  const nodeSystem = new THREE.Group();
  orbit.add(pivot);
  pivot.rotation.y = angle;
  pivot.add(nodeSystem);
  // The orbit offset lives on nodeSystem (not the mesh) so the mesh can self-spin
  // in place while this page's children orbit its position without whirling.
  nodeSystem.position.set(radius, y, 0);
  parentSystem.add(orbit);

  let mesh;
  if (isRoot) {
    mesh = makeSun(node);
    if (radius > 0) {
      const sunLight = new THREE.PointLight(0xfff2d6, 1.6, 0, 0);
      mesh.add(sunLight);
    }
  } else {
    mesh = makePlanet(node);
  }
  mesh.userData.node = node;
  nodeSystem.add(mesh);

  planetById.set(node.id, mesh);
  planets.push({
    node,
    mesh,
    pivot,
    orbitSpeed,
    selfSpeed: 0.12 + (hashString(node.id) % 100) / 320,
  });
  return nodeSystem;
}

// Soft radial-gradient glow reused by the sun's corona and red-dwarf halos.
function makeGlowTexture() {
  const size = 256;
  const cv = document.createElement("canvas");
  cv.width = size;
  cv.height = size;
  const ctx = cv.getContext("2d");
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  g.addColorStop(0.0, "rgba(255,246,220,0.95)");
  g.addColorStop(0.25, "rgba(255,205,125,0.55)");
  g.addColorStop(0.55, "rgba(255,150,70,0.2)");
  g.addColorStop(1.0, "rgba(255,140,60,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, size, size);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
const GLOW_TEXTURE = makeGlowTexture();
const coronas = []; // { sprite, baseR } — updated by zoom in animate()

function makeSun(node) {
  const r = SUN_R + clamp01(Number(node.size_scale) || 0) * 1.6;
  const sun = new THREE.Mesh(
    new THREE.SphereGeometry(r, 40, 40),
    new THREE.MeshBasicMaterial({ color: 0xffe6b0 }),
  );
  // Additive corona sprite always faces the camera; animate() scales + fades it
  // with zoom so the star is soft up close and blazing from afar.
  const corona = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: GLOW_TEXTURE,
      color: 0xffc46b,
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
      opacity: 0.5,
    }),
  );
  corona.scale.setScalar(r * 7);
  sun.add(corona);
  coronas.push({ sprite: corona, baseR: r });
  // Swap in the real sun texture when reachable; keep the warm sphere otherwise.
  loadCdnTexture("sun.jpg", (tex) => {
    sun.material.map = tex;
    sun.material.color.set(0xffffff);
    sun.material.needsUpdate = true;
  });
  return sun;
}

function makePlanet(node) {
  if (node.color_category === "fail") return makeRedDwarf(node);
  const r = planetRadius(node);
  const isGiant = Boolean(node.is_giant);
  const bucket = Math.max(0, Math.min(3, Math.floor((Number(node.richness) || 0) * 4)));
  let pal;
  let palKey;
  let texFile;
  if (isGiant) {
    pal = SATURN_PAL;
    palKey = "saturn";
    texFile = GIANT_TEX;
  } else if (node.color_category === "success") {
    const idx = hashString(node.url) % SUCCESS_BIOMES.length;
    pal = SUCCESS_BIOMES[idx];
    palKey = "s" + idx;
    texFile = SUCCESS_BIOME_TEX[idx];
  } else {
    pal = PALETTE[node.color_category] || PALETTE.discovered;
    palKey = node.color_category;
    texFile = CATEGORY_TEX[node.color_category];
  }
  const mat = new THREE.MeshStandardMaterial({
    map: planetTexture(palKey, pal, bucket, isGiant),
    roughness: 0.8,
    metalness: 0.0,
  });
  applyCdnTexture(mat, texFile);
  if (node.retry) {
    mat.emissive = new THREE.Color(RETRY_EMISSIVE);
    mat.emissiveIntensity = 0.14;
  }
  const mesh = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 32), mat);
  mesh.rotation.z = (hashString(node.id) % 40) / 100 - 0.2; // gentle axial tilt
  if (isGiant) mesh.add(makeRing(r));
  return mesh;
}

// Failed pages become dim red-dwarf stars: small, cool, faintly glowing embers.
function makeRedDwarf(node) {
  const r = MIN_PLANET_R + clamp01(Number(node.size_scale) || 0) * 0.9;
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(r, 24, 24),
    new THREE.MeshStandardMaterial({
      color: 0x3a0f08,
      emissive: 0xff4a2a,
      emissiveIntensity: 0.9,
      roughness: 1.0,
    }),
  );
  const glow = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: GLOW_TEXTURE,
      color: 0xff5a34,
      blending: THREE.AdditiveBlending,
      transparent: true,
      depthWrite: false,
      opacity: 0.5,
    }),
  );
  glow.scale.setScalar(r * 5);
  mesh.add(glow);
  return mesh;
}

function smooth01(x, a, b) {
  return clamp01((x - a) / (b - a));
}

// Procedural Saturn ring: concentric bands, a Cassini-division gap, and faded
// inner/outer edges. Mapped radially by makeRing so the bands follow radius.
function makeSaturnRingTexture() {
  const w = 512;
  const h = 12;
  const cv = document.createElement("canvas");
  cv.width = w;
  cv.height = h;
  const ctx = cv.getContext("2d");
  ctx.clearRect(0, 0, w, h);
  const rand = mulberry32(0x5a7);
  for (let x = 0; x < w; x++) {
    const tt = x / (w - 1); // 0 = inner edge, 1 = outer edge
    let a = 0.45 + 0.4 * (0.5 + 0.5 * Math.sin(tt * 46)) + 0.15 * rand();
    if (tt > 0.6 && tt < 0.66) a *= 0.08; // Cassini division gap
    a *= Math.min(smooth01(tt, 0, 0.05), smooth01(1 - tt, 0, 0.09)); // fade edges
    const s = 175 + Math.floor(rand() * 55);
    ctx.fillStyle = `rgba(${s + 22},${s + 6},${s - 16},${clamp01(a)})`;
    ctx.fillRect(x, 0, 1, h);
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
const SATURN_RING_TEXTURE = makeSaturnRingTexture();

function makeRing(planetR) {
  const inner = planetR * 1.35;
  const outer = planetR * 2.35;
  const geo = new THREE.RingGeometry(inner, outer, 128, 4);
  // Remap UVs radially so the ring texture's bands + Cassini gap follow radius.
  const pos = geo.attributes.position;
  const uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    const d = Math.hypot(pos.getX(i), pos.getY(i));
    uv.setXY(i, (d - inner) / (outer - inner), 0.5);
  }
  uv.needsUpdate = true;
  const ring = new THREE.Mesh(
    geo,
    new THREE.MeshBasicMaterial({
      map: SATURN_RING_TEXTURE,
      transparent: true,
      opacity: 0.9,
      side: THREE.DoubleSide,
      depthWrite: false,
    }),
  );
  applyCdnTexture(ring.material, "saturn_ring.png");
  ring.rotation.x = Math.PI / 2 - 0.42;
  ring.rotation.z = 0.16;
  return ring;
}

const outerRadius = buildLayout();

// Zoom-responsive sun: soft up close, blazing when far (distance to the centre).
const SUN_NEAR = 32;
const SUN_FAR = outerRadius * 2.2 + 90;
const SUN_BLOOM_NEAR = 0.55;
const SUN_BLOOM_FAR = 1.95;

// ── Connection lines (parent → child), updated each frame ────────────────────
const edges = (Array.isArray(MODEL.edges) ? MODEL.edges : []).filter(
  (e) => planetById.has(e.source) && planetById.has(e.target),
);
const LINE_BASE = new THREE.Color(0x6b7280); // neutral grey (default connections)
const LINE_DIM = new THREE.Color(0x191c22); // near-invisible while a planet is focused
// The focused chain renders as a "Petrova line" (Project Hail Mary): a steady
// crimson thread carrying a hot, white-pink light knot that flows from the sun
// outward. The crest is pushed HDR so the scene's bloom turns it into a glowing
// beam and ACES tone-mapping renders the knot's core white-hot; a hovered chain
// gets a calmer static crimson so it reads as secondary to the selection.
const PETROVA_CORE = new THREE.Color(0xff1e3c); // steady crimson beam body
const PETROVA_HOT = new THREE.Color(0xffdbe4); // hot pink-white crest core (blooms white)
const PETROVA_HOVER = new THREE.Color(0xff2a44); // static soft crimson for a hovered chain
const PULSE_SPEED = 2.6; // radians/sec of the light knot flowing along the chain
const PULSE_WAVES = 1.5; // number of light knots travelling the chain at once
const PETROVA_TROUGH = 0.9; // steady crimson brightness between knots
const PETROVA_CREST = 3.5; // HDR crest gain so a knot blooms into a white-hot glow
const _pulse = new THREE.Color();
let linkMesh = null;
let linkPositions = null;
let linkColors = null;

function buildLinks() {
  if (edges.length === 0) return;
  const verts = edges.length * SEG_PER_EDGE * 2;
  linkPositions = new Float32Array(verts * 3);
  linkColors = new Float32Array(verts * 3);
  for (let v = 0; v < verts; v++) LINE_BASE.toArray(linkColors, v * 3);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(linkPositions, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(linkColors, 3));
  linkMesh = new THREE.LineSegments(
    geo,
    new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.55,
      depthWrite: false,
    }),
  );
  systemGroup.add(linkMesh);
}
buildLinks();

const _a = new THREE.Vector3();
const _b = new THREE.Vector3();
const _ctrl = new THREE.Vector3();
const _dir = new THREE.Vector3();
const _p = new THREE.Vector3();
const _q = new THREE.Vector3();

// Quadratic Bézier point at t into `out` (alloc-free).
function quadPoint(a, ctrl, b, tt, out) {
  const u = 1 - tt;
  return out
    .set(0, 0, 0)
    .addScaledVector(a, u * u)
    .addScaledVector(ctrl, 2 * u * tt)
    .addScaledVector(b, tt * tt);
}

function updateLinks() {
  if (!linkMesh) return;
  const stride = SEG_PER_EDGE * 2 * 3;
  for (let i = 0; i < edges.length; i++) {
    planetById.get(edges[i].source).getWorldPosition(_a);
    planetById.get(edges[i].target).getWorldPosition(_b);
    systemGroup.worldToLocal(_a);
    systemGroup.worldToLocal(_b);
    // Bow the link outward from the centre and lift it in Y so it reads like an
    // orbital-transfer trajectory rather than a straight spoke.
    _ctrl.addVectors(_a, _b).multiplyScalar(0.5);
    const span = _a.distanceTo(_b);
    _dir.copy(_ctrl);
    if (_dir.lengthSq() > 1e-6) _dir.normalize();
    else _dir.set(0, 1, 0);
    _ctrl.addScaledVector(_dir, span * 0.28);
    _ctrl.y += span * 0.24 + 2;
    let off = i * stride;
    for (let s = 0; s < SEG_PER_EDGE; s++) {
      quadPoint(_a, _ctrl, _b, s / SEG_PER_EDGE, _p);
      quadPoint(_a, _ctrl, _b, (s + 1) / SEG_PER_EDGE, _q);
      _p.toArray(linkPositions, off);
      _q.toArray(linkPositions, off + 3);
      off += 6;
    }
  }
  linkMesh.geometry.attributes.position.needsUpdate = true;
}

// Precompute the ordered edge chain from a node up to its root (root-first) so
// the highlight can flow outward from the sun.
function orderedChain(nodeId) {
  const chain = [];
  let current = nodeId;
  let guard = 0;
  while (current && guard++ < 4096) {
    const node = nodeById.get(current);
    if (!node || !node.parent) break;
    for (let i = 0; i < edges.length; i++) {
      if (edges[i].target === current && edges[i].source === node.parent) {
        chain.push(i);
        break;
      }
    }
    current = node.parent;
  }
  chain.reverse();
  return chain;
}

// Paint every link once per change: dim base, a static crimson hover chain, and
// the animated red "Petrova line" pulse that flows along the focused chain.
function paintLinks(elapsed) {
  if (!linkMesh) return;
  const perEdge = SEG_PER_EDGE * 2;
  for (let i = 0; i < edges.length; i++) {
    const base = i * perEdge * 3;
    if (focusChain && focusChain.has(i)) {
      const j = focusOrder.get(i);
      for (let seg = 0; seg < SEG_PER_EDGE; seg++) {
        writePulse(base + seg * 6, (j + seg / SEG_PER_EDGE) / focusLen, elapsed);
        writePulse(base + seg * 6 + 3, (j + (seg + 1) / SEG_PER_EDGE) / focusLen, elapsed);
      }
      continue;
    }
    // Non-focus edges: a hovered chain stays a static crimson; the rest fade to
    // near-invisible while a planet is selected so its trajectory reads clearly.
    const c = hoverChain && hoverChain.has(i) ? PETROVA_HOVER : focusChain ? LINE_DIM : LINE_BASE;
    for (let v = 0; v < perEdge; v++) c.toArray(linkColors, base + v * 3);
  }
  linkMesh.geometry.attributes.color.needsUpdate = true;
}

function writePulse(offset, s, elapsed) {
  const wave = 0.5 + 0.5 * Math.sin(elapsed * PULSE_SPEED - s * PULSE_WAVES * Math.PI * 2);
  const knot = wave * wave; // concentrate brightness into a travelling knot of light
  _pulse
    .copy(PETROVA_CORE)
    .lerp(PETROVA_HOT, knot)
    .multiplyScalar(PETROVA_TROUGH + PETROVA_CREST * knot);
  _pulse.toArray(linkColors, offset);
}

// ── Camera framing + reset ───────────────────────────────────────────────────
const homeTarget = new THREE.Vector3(0, 0, 0);
const homePos = new THREE.Vector3(0, outerRadius * 0.6 + 10, outerRadius * 1.15 + 20);
camera.position.copy(homePos);
controls.target.copy(homeTarget);
controls.maxDistance = outerRadius * 6 + 400;
controls.update();

function resetView() {
  setFocus(null);
  markInteract();
  camera.position.copy(homePos);
  controls.target.copy(homeTarget);
  controls.update();
}

// ── Static HUD text: stats, help, legend ─────────────────────────────────────
function renderHud() {
  const stats = MODEL.stats || {};
  const by = stats.by_status || {};
  const parts = [`<span><b>${stats.total || 0}</b> ${t("hud_pages", "Pages")}</span>`];
  parts.push(`<span><b>${stats.max_depth || 0}</b> ${t("hud_depth", "Max depth")}</span>`);
  document.getElementById("sg-stats").innerHTML = parts.join("");

  const rows = [
    ["ctrl_rotate", "ctrl_rotate_hint"],
    ["ctrl_pan", "ctrl_pan_hint"],
    ["ctrl_zoom", "ctrl_zoom_hint"],
    ["ctrl_move", "ctrl_move_hint"],
    ["ctrl_reset", "ctrl_reset_hint"],
    ["ctrl_focus", "ctrl_focus_hint"],
  ];
  document.getElementById("sg-help-body").innerHTML = rows
    .map(
      ([act, key]) =>
        `<span class="sg-key">${esc(t(key))}</span><span class="sg-act">${esc(t(act))}</span>`,
    )
    .join("");

  const legendOrder = ["success", "fail", "skipped", "discovered"];
  document.getElementById("sg-legend").innerHTML = legendOrder
    .filter((s) => by[s])
    .map(
      (s) =>
        `<span class="sg-dot"><span class="sg-swatch" style="color:${STATUS_CSS[s]}"></span>` +
        `${esc(t("status_" + s))} <b style="color:var(--sg-text)">${by[s]}</b></span>`,
    )
    .join("");
}
renderHud();

// ── Hover + selection ────────────────────────────────────────────────────────
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
const meshes = planets.map((p) => p.mesh);
let hovered = null;
let lastHover = 0;
let pointerDown = null;

function setPointer(ev) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1;
}

function pick() {
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(meshes, false);
  return hits.length ? hits[0].object : null;
}

function onPointerMove(ev) {
  const now = performance.now();
  if (now - lastHover < HOVER_MS) {
    positionTooltip(ev);
    return;
  }
  lastHover = now;
  setPointer(ev);
  const mesh = pick();
  if (mesh !== hovered) {
    if (hovered) hovered.scale.setScalar(1);
    hovered = mesh;
    if (hovered) {
      hovered.scale.setScalar(1.16);
      hoverChain = new Set(orderedChain(hovered.userData.node.id));
      linksDirty = true;
      showTooltip(hovered.userData.node);
    } else {
      hoverChain = null;
      linksDirty = true;
      hideTooltip();
    }
  }
  positionTooltip(ev);
}

function onPointerDown(ev) {
  pointerDown = { x: ev.clientX, y: ev.clientY };
  markInteract();
  if (ev.button === 2) followFocus = false; // right-drag pans freely, unlocked
}
function onPointerUp(ev) {
  if (!pointerDown) return;
  const moved = Math.hypot(ev.clientX - pointerDown.x, ev.clientY - pointerDown.y);
  pointerDown = null;
  if (moved > CLICK_DRAG_PX) return; // was a drag (rotate/pan), not a click
  setPointer(ev);
  const mesh = pick();
  if (!mesh || mesh === focusMesh) {
    closeInfo(); // empty space or re-clicking the focused planet toggles it off
    return;
  }
  openInfo(mesh.userData.node);
  setFocus(mesh);
}

// ── Tooltip ──────────────────────────────────────────────────────────────────
function showTooltip(node) {
  const rows = [];
  rows.push(`<div class="sg-tt-url">${esc(node.url)}</div>`);
  rows.push(row(t("panel_status"), statusLabel(node)));
  rows.push(row(t("panel_depth"), String(node.depth)));
  if (node.page_size_kb != null) rows.push(row(t("panel_size"), fmtSize(node.page_size_kb)));
  rows.push(row(t("panel_links"), String(node.child_count)));
  if (node.round_num != null) rows.push(row(t("panel_round"), String(node.round_num)));
  tooltipEl.innerHTML = rows.join("");
  tooltipEl.setAttribute("data-show", "true");
}
function row(key, val) {
  return `<div class="sg-tt-row"><b>${esc(key)}:</b> ${esc(val)}</div>`;
}
function positionTooltip(ev) {
  if (tooltipEl.getAttribute("data-show") !== "true") return;
  const pad = 16;
  const rect = tooltipEl.getBoundingClientRect();
  let x = ev.clientX + pad;
  let y = ev.clientY + pad;
  if (x + rect.width > window.innerWidth) x = ev.clientX - rect.width - pad;
  if (y + rect.height > window.innerHeight) y = ev.clientY - rect.height - pad;
  tooltipEl.style.left = `${Math.max(4, x)}px`;
  tooltipEl.style.top = `${Math.max(4, y)}px`;
}
function hideTooltip() {
  tooltipEl.setAttribute("data-show", "false");
}

// ── Detail panel ─────────────────────────────────────────────────────────────
let previewTimer = null;
function openInfo(node) {
  infoTitle.textContent = node.url;
  const fields = [];
  fields.push(
    node.is_root
      ? fieldRow(t("panel_discovered_from"), t("panel_seed"))
      : fieldRow(t("panel_discovered_from"), node.discovered_from || "—"),
  );
  fields.push(fieldBadge(t("panel_status"), node));
  fields.push(fieldRow(t("panel_depth"), String(node.depth)));
  fields.push(
    fieldRow(t("panel_size"), node.page_size_kb != null ? fmtSize(node.page_size_kb) : "—"),
  );
  fields.push(fieldRow(t("panel_links"), String(node.child_count)));
  fields.push(fieldRow(t("panel_round"), node.round_num != null ? String(node.round_num) : "—"));
  infoFields.innerHTML = fields.join("");

  const safeUrl = safeHttpUrl(node.url);
  openPageEl.href = safeUrl || "#";
  openPageEl.textContent = `\u2197  ${t("panel_open_page", "Open page in new tab")}`;

  previewMsg.textContent = t("panel_preview_loading", "Loading live preview\u2026");
  previewMsg.style.display = "flex";
  if (previewTimer) clearTimeout(previewTimer);
  if (safeUrl) {
    previewEl.src = safeUrl;
    previewTimer = setTimeout(() => {
      previewMsg.textContent = t("panel_preview_blocked", "");
    }, PREVIEW_TIMEOUT_MS);
  } else {
    previewEl.src = "about:blank";
    previewMsg.textContent = t("panel_preview_blocked", "");
  }

  infoEl.setAttribute("data-open", "true");
}
previewEl.addEventListener("load", () => {
  if (previewTimer) clearTimeout(previewTimer);
  previewMsg.style.display = "none";
});
function closeInfo() {
  infoEl.setAttribute("data-open", "false");
  if (previewTimer) clearTimeout(previewTimer);
  previewEl.src = "about:blank";
  setFocus(null);
}
document.getElementById("sg-info-close").addEventListener("click", closeInfo);

function fieldRow(key, val) {
  return `<span class="sg-f-key">${esc(key)}</span><span class="sg-f-val">${esc(val)}</span>`;
}
function fieldBadge(key, node) {
  const color = STATUS_CSS[node.color_category] || STATUS_CSS.discovered;
  return (
    `<span class="sg-f-key">${esc(key)}</span>` +
    `<span class="sg-f-val"><span class="sg-badge" style="color:${color}">${esc(statusLabel(node))}</span></span>`
  );
}
function statusLabel(node) {
  return t("status_" + node.color_category, node.status);
}

// ── Help toggle ──────────────────────────────────────────────────────────────
const helpEl = document.getElementById("sg-help");
document.getElementById("sg-help-toggle").addEventListener("click", () => {
  const collapsed = helpEl.getAttribute("data-collapsed") === "true";
  helpEl.setAttribute("data-collapsed", collapsed ? "false" : "true");
});

// ── Keyboard navigation ──────────────────────────────────────────────────────
const keys = new Set();
const MOVE_KEYS = new Set([
  "KeyW", "KeyA", "KeyS", "KeyD",
  "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
]);
window.addEventListener("keydown", (e) => {
  markInteract();
  if (e.code === "KeyR") {
    resetView();
    return;
  }
  if (MOVE_KEYS.has(e.code)) {
    keys.add(e.code);
    e.preventDefault();
  }
});
window.addEventListener("keyup", (e) => keys.delete(e.code));

const _right = new THREE.Vector3();
const _up = new THREE.Vector3();
const _move = new THREE.Vector3();
function applyKeyboard(dt) {
  if (keys.size === 0) return;
  let dx = 0;
  let dy = 0;
  if (keys.has("KeyD") || keys.has("ArrowRight")) dx += 1;
  if (keys.has("KeyA") || keys.has("ArrowLeft")) dx -= 1;
  if (keys.has("KeyW") || keys.has("ArrowUp")) dy += 1;
  if (keys.has("KeyS") || keys.has("ArrowDown")) dy -= 1;
  if (dx === 0 && dy === 0) return;
  const dist = camera.position.distanceTo(controls.target);
  const step = KEY_PAN_SPEED * dt * Math.max(dist * 0.05, 1);
  _right.setFromMatrixColumn(camera.matrixWorld, 0); // camera right
  _up.setFromMatrixColumn(camera.matrixWorld, 1); // camera up
  _move
    .set(0, 0, 0)
    .addScaledVector(_right, dx * step)
    .addScaledVector(_up, dy * step);
  camera.position.add(_move);
  controls.target.add(_move);
}

// ── Resize ───────────────────────────────────────────────────────────────────
function onResize() {
  const w = window.innerWidth;
  const h = window.innerHeight;
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  renderer.setSize(w, h);
  composer.setSize(w, h);
  bloomPass.resolution.set(w, h);
}
window.addEventListener("resize", onResize);

renderer.domElement.addEventListener("pointermove", onPointerMove);
renderer.domElement.addEventListener("pointerdown", onPointerDown);
renderer.domElement.addEventListener("pointerup", onPointerUp);

// ── Animation loop ───────────────────────────────────────────────────────────
const clock = new THREE.Clock();
function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);
  // Ambient motion (planet orbit + spin, starfield drift, camera auto-revolve)
  // plays only when idle, eased in/out via idleFactor so it glides rather than
  // snaps the moment the user grabs or releases the scene.
  const idle = performance.now() - lastInteract > IDLE_MS;
  idleFactor = THREE.MathUtils.damp(idleFactor, idle ? 1 : 0, IDLE_RAMP_LAMBDA, dt);
  for (const p of planets) {
    if (p.orbitSpeed) p.pivot.rotation.y += p.orbitSpeed * dt * idleFactor;
    p.mesh.rotation.y += p.selfSpeed * dt * idleFactor;
  }
  starfield.rotation.y += dt * 0.005 * idleFactor;
  const zoom = THREE.MathUtils.clamp(
    (camera.position.length() - SUN_NEAR) / (SUN_FAR - SUN_NEAR),
    0,
    1,
  );
  bloomPass.strength = THREE.MathUtils.lerp(SUN_BLOOM_NEAR, SUN_BLOOM_FAR, zoom);
  for (const c of coronas) {
    c.sprite.material.opacity = THREE.MathUtils.lerp(0.3, 0.72, zoom);
    c.sprite.scale.setScalar(c.baseR * THREE.MathUtils.lerp(5, 9.5, zoom));
  }
  // Follow the focused planet (as it orbits) until the user pans away; the
  // camera auto-revolve eases in with idleFactor (scaled speed) so it glides to
  // a stop when the user grabs the scene and back up once idle.
  if (focusMesh && followFocus) {
    focusMesh.getWorldPosition(_focusPos);
    controls.target.lerp(_focusPos, 0.12);
  }
  controls.autoRotate = true;
  controls.autoRotateSpeed = AUTO_ROTATE_SPEED * idleFactor;
  applyKeyboard(dt);
  controls.update();
  scene.updateMatrixWorld(true);
  updateLinks();
  const elapsed = clock.getElapsedTime();
  if (focusChain) {
    paintLinks(elapsed);
    if (focusHalo) focusHalo.material.opacity = 0.55 + 0.3 * Math.sin(elapsed * PULSE_SPEED);
  } else if (linksDirty) {
    paintLinks(elapsed);
    linksDirty = false;
  }
  composer.render();
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function fmtSize(kb) {
  const n = Number(kb);
  if (n >= 1024) return `${(n / 1024).toFixed(2)} MB`;
  return `${n.toFixed(n < 10 ? 2 : 1)} KB`;
}
function esc(value) {
  return String(value == null ? "" : value).replace(
    /[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch],
  );
}

function safeHttpUrl(url) {
  // Only ever navigate/frame http(s); never a javascript:/data: URL from data.
  const s = String(url == null ? "" : url).trim();
  return /^https?:\/\//i.test(s) ? s : "";
}

animate();
