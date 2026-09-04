// Standalone 3D "crawl universe" scene. Inlined into the self-contained page the
// launcher opens in a new tab; three.js loads from the pinned CDN via the import
// map in viewer.html. Reads the crawl model from window.__SITE_GRAPH__ and the
// localized labels from window.__VIEWER_LABELS__.
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { ShaderPass } from "three/addons/postprocessing/ShaderPass.js";
import {
  forceSimulation,
  forceManyBody,
  forceLink,
  forceCollide,
  forceX,
  forceY,
} from "d3-force";

// ── Data + labels ────────────────────────────────────────────────────────────
const MODEL = window.__SITE_GRAPH__ || { nodes: [], edges: [], root_ids: [], stats: {} };
const L = window.__VIEWER_LABELS__ || {};
const t = (key, fallback) => (L[key] != null ? L[key] : fallback != null ? fallback : key);

// ── Tuning constants ─────────────────────────────────────────────────────────
const MIN_PLANET_R = 0.6;
const MAX_PLANET_R = 3.0;
const SUN_R = 3.4;
const SUN_CLEARANCE = 9; // min camera clearance from the central sun
const AUTO_ROTATE_SPEED = 0.2; // idle camera auto-revolve speed (OrbitControls units)
// Planet positions are computed in the browser by a d3-force simulation (see
// runForceLayout below): pages repel, parent→child links attract, collision +
// centre-gravity keep the whole crawl compact, and the seed page is pinned as
// the central sun — so a large, deep crawl reads as clustered constellations.
const SEG_PER_EDGE = 18; // samples per link (kept so the flow-pulse can run along it)
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

// ── Post-processing ──────────────────────────────────────────────────────────
// A screen-space gravitational-lensing pass warps the rendered image around each
// black hole (light bending) and draws its photon ring; bloom then makes the suns
// and that ring glow. Capped at MAX_LENSED_HOLES per frame and disabled entirely
// when the crawl has no failed pages, so it costs nothing in the common case.
const MAX_LENSED_HOLES = 6;
const blackHoles = []; // { mesh, radius } — projected to screen space each frame
const blackHoleLensShader = {
  uniforms: {
    tDiffuse: { value: null },
    resolution: { value: new THREE.Vector2(window.innerWidth, window.innerHeight) },
    holeCount: { value: 0 },
    holeCenter: {
      value: Array.from({ length: MAX_LENSED_HOLES }, () => new THREE.Vector2()),
    },
    holeRadius: { value: new Float32Array(MAX_LENSED_HOLES) },
  },
  vertexShader: /* glsl */ `
    varying vec2 vUv;
    void main() {
      vUv = uv;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
    }
  `,
  fragmentShader: /* glsl */ `
    #define MAX_HOLES ${MAX_LENSED_HOLES}
    uniform sampler2D tDiffuse;
    uniform vec2 resolution;
    uniform int holeCount;
    uniform vec2 holeCenter[MAX_HOLES];
    uniform float holeRadius[MAX_HOLES];
    varying vec2 vUv;
    void main() {
      float aspect = resolution.x / resolution.y;
      vec3 color = texture2D(tDiffuse, vUv).rgb;
      vec3 ring = vec3(0.0);
      float shadow = 0.0;
      for (int i = 0; i < MAX_HOLES; i++) {
        if (i >= holeCount) break;
        float rs = holeRadius[i];
        if (rs <= 0.0) continue;
        vec2 d = vUv - holeCenter[i];
        d.x *= aspect;                        // isotropic (screen-height) units
        float dist = length(d);
        vec2 dir = dist > 1e-4 ? d / dist : vec2(0.0);
        // Bend light toward the mass ~ rs^2 / dist, strongest at the horizon and
        // fading to nothing a few radii out so the far field stays untouched.
        float defl = min(rs * rs / max(dist, 1e-4), rs * 3.0);
        float influence = smoothstep(rs * 5.0, rs * 1.05, dist);
        vec2 warp = vec2(dir.x / aspect, dir.y) * defl * influence;
        color = texture2D(tDiffuse, vUv - warp).rgb;
        // Photon ring: a thin warm band hugging the horizon (bloom lights it up).
        float band = smoothstep(rs * 1.5, rs * 1.08, dist) *
                     smoothstep(rs * 0.92, rs * 1.06, dist);
        ring += vec3(1.0, 0.72, 0.38) * band * 1.6;
        // Event-horizon shadow: the dark disc the light bends around.
        shadow = max(shadow, smoothstep(rs * 1.04, rs * 0.97, dist));
      }
      color = mix(color, vec3(0.0), shadow);
      color += ring;
      gl_FragColor = vec4(color, 1.0);
    }
  `,
};

const composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
const lensPass = new ShaderPass(blackHoleLensShader);
lensPass.enabled = false; // switched on in animate() only while holes are on-screen
composer.addPass(lensPass);
const bloomPass = new UnrealBloomPass(
  new THREE.Vector2(window.innerWidth, window.innerHeight),
  1.15, // strength
  0.55, // radius
  0.62, // threshold — only bright emissive suns bloom
);
composer.addPass(bloomPass);

// Reused temporaries for projecting each black hole to screen space each frame.
const _lensWorld = new THREE.Vector3();
const _lensCenter = new THREE.Vector3();
const _lensEdge = new THREE.Vector3();
const _lensUp = new THREE.Vector3();

function updateLensUniforms() {
  const u = lensPass.uniforms;
  camera.updateMatrixWorld(); // refresh matrixWorldInverse so project() isn't a frame behind
  _lensUp.setFromMatrixColumn(camera.matrixWorld, 1); // world-space camera up
  let count = 0;
  for (const bh of blackHoles) {
    if (count >= MAX_LENSED_HOLES) break;
    bh.mesh.getWorldPosition(_lensWorld);
    _lensCenter.copy(_lensWorld).project(camera);
    if (_lensCenter.z > 1.0) continue; // behind the camera / beyond the far plane
    _lensEdge.copy(_lensWorld).addScaledVector(_lensUp, bh.radius).project(camera);
    const radiusUv = Math.abs(_lensEdge.y - _lensCenter.y) * 0.5;
    if (radiusUv <= 0.0) continue;
    u.holeCenter.value[count].set(_lensCenter.x * 0.5 + 0.5, _lensCenter.y * 0.5 + 0.5);
    u.holeRadius.value[count] = radiusUv;
    count++;
  }
  u.holeCount.value = count;
  lensPass.enabled = count > 0;
}

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

// Positions are computed here in the browser by a force-directed simulation
// (d3-force): pages repel, parent→child links pull together, a collision force
// keeps bodies from stacking, and a gentle pull to the centre keeps the whole
// site compact — so a large, deep crawl reads as clustered constellations, not a
// sprawl. One seed page is pinned at the origin as the central sun; the run is
// seeded per crawl so a given graph settles the same way every time it opens.
const FORCE_CHARGE = -26; // node-to-node repulsion (negative = repel)
const FORCE_CHARGE_MAX = 260; // cap repulsion range so distant clusters don't blow apart
const FORCE_LINK_DIST = 9; // desired parent→child spacing (world units)
const FORCE_LINK_STRENGTH = 0.72;
const FORCE_COLLIDE_GAP = 0.8; // clearance added to each body radius
const FORCE_GRAVITY = 0.045; // pull toward the centre (keeps the layout compact)
const FORCE_TICKS_MIN = 150;
const FORCE_TICKS_MAX = 420;

const rootIds = new Set(
  nodes.filter((n) => n.is_root || !nodeById.has(n.parent)).map((n) => n.id),
);

function bodyRadius(node, isRoot) {
  return isRoot ? SUN_R + clamp01(Number(node.size_scale) || 0) * 1.6 : planetRadius(node);
}

function runForceLayout() {
  const simNodes = nodes.map((n) => ({ id: n.id, r: bodyRadius(n, rootIds.has(n.id)) }));
  const present = new Set(simNodes.map((s) => s.id));
  const simLinks = (Array.isArray(MODEL.edges) ? MODEL.edges : [])
    .filter((e) => present.has(e.source) && present.has(e.target))
    .map((e) => ({ source: e.source, target: e.target }));
  // Seed Math.random so d3-force's collision jitter settles a crawl the same way each open.
  const seededRandom = mulberry32(hashString(simNodes.length + ":" + (simNodes[0]?.id || "")));
  const originalRandom = Math.random;
  Math.random = seededRandom;
  try {
    const sim = forceSimulation(simNodes)
      .force("charge", forceManyBody().strength(FORCE_CHARGE).distanceMax(FORCE_CHARGE_MAX))
      .force(
        "link",
        forceLink(simLinks)
          .id((d) => d.id)
          .distance(FORCE_LINK_DIST)
          .strength(FORCE_LINK_STRENGTH),
      )
      .force("collide", forceCollide().radius((d) => d.r + FORCE_COLLIDE_GAP).iterations(2))
      .force("x", forceX(0).strength(FORCE_GRAVITY))
      .force("y", forceY(0).strength(FORCE_GRAVITY))
      .stop();
    let pinned = false;
    for (const s of simNodes) {
      if (!pinned && rootIds.has(s.id)) {
        s.fx = 0;
        s.fy = 0;
        pinned = true;
      }
    }
    const ticks = Math.max(
      FORCE_TICKS_MIN,
      Math.min(FORCE_TICKS_MAX, Math.round(140 + simNodes.length * 0.12)),
    );
    for (let i = 0; i < ticks; i++) sim.tick();
  } finally {
    Math.random = originalRandom;
  }
  const positions = new Map();
  for (const s of simNodes) positions.set(s.id, { x: s.x || 0, y: s.y || 0 });
  return positions;
}

const forcePositions = runForceLayout();

// The force layout is flat (one plane), so links all cross on that single plane.
// Lift it into a shallow bowl — each body rises with its distance from the centre
// — so links spread through depth and the crawl reads as a dome/flower, not a
// tangled disc. The seed sun stays at the origin (rise 0) as the low centre.
const DOME_LIFT = 0.2; // rim height as a fraction of the layout radius (0 = flat)
let layoutRadius = SUN_CLEARANCE;
for (const p of forcePositions.values()) {
  layoutRadius = Math.max(layoutRadius, Math.hypot(p.x, p.y));
}
function domeLift(p) {
  const t = layoutRadius > 0 ? Math.hypot(p.x, p.y) / layoutRadius : 0;
  return DOME_LIFT * layoutRadius * (1 - Math.cos(t * Math.PI * 0.5));
}

function buildLayout() {
  let outer = SUN_CLEARANCE;
  for (const node of nodes) {
    createBody(node, rootIds.has(node.id));
    const p = forcePositions.get(node.id) || { x: 0, y: 0 };
    outer = Math.max(outer, Math.hypot(p.x, p.y));
  }
  return outer;
}

function createBody(node, isRoot) {
  const mesh = isRoot ? makeSun(node) : makePlanet(node);
  const p = forcePositions.get(node.id) || { x: 0, y: 0 };
  mesh.position.set(p.x, domeLift(p), p.y);
  // An offset seed sun (multi-root crawl) lights its neighbourhood; the central
  // sun at the origin is already lit by the scene's central light.
  if (isRoot && mesh.position.length() > 1e-3) {
    mesh.add(new THREE.PointLight(0xfff2d6, 1.6, 0, 0));
  }
  mesh.userData.node = node;
  systemGroup.add(mesh);
  planetById.set(node.id, mesh);
  planets.push({ node, mesh, selfSpeed: 0.12 + (hashString(node.id) % 100) / 320 });
}

// Soft radial-gradient glow reused by the sun's corona and the focus halo.
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
  if (node.color_category === "fail") return makeBlackHole(node);
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

// Failed pages collapse into black holes: a pure-black event horizon that emits
// no light of its own. The screen-space lensing pass warps the starfield around
// it and draws its photon ring, so it reads as a dark body — a planet-like mass,
// not a light source. A pulsar-style beacon (below) makes it easy to spot.
const beacons = []; // { material } — the pulsar beacons pulsed each frame
const BEACON_PULSE_SPEED = 3.2; // radians/sec of the beacon's brightness pulse
const BEACON_LEN_SCALE = 6; // beam length as a multiple of the hole radius
const BEACON_LEN_MIN = 2.5; // floor so even tiny holes get a visible beam (scene units)
const BEACON_RADIUS_SCALE = 0.32; // beam base radius as a multiple of the hole radius
const BEACON_HUE = 0xffb84d; // warm photon-ring hue, matching the black-hole look
const BEACON_OPACITY = 0.34; // base additive opacity — a gentle glow, kept narrow

// A pulsar-style beacon: two opposed beams tapering to a point along the vertical
// axis so a failed page's black hole stands out among many planets. Pure additive
// geometry with NO THREE.Light, so it never illuminates other bodies; kept narrow
// and dim so the bloom pass only glows it gently, never washing its neighbours.
function makeBlackHoleBeacon(r) {
  const beamLen = r * BEACON_LEN_SCALE + BEACON_LEN_MIN;
  const beamR = r * BEACON_RADIUS_SCALE;
  const material = new THREE.MeshBasicMaterial({
    color: BEACON_HUE,
    transparent: true,
    opacity: BEACON_OPACITY,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const group = new THREE.Group();
  for (const dir of [1, -1]) {
    // Open-ended cone: base at the pole, apex tapering outward (no bright end cap).
    const cone = new THREE.Mesh(new THREE.ConeGeometry(beamR, beamLen, 12, 1, true), material);
    cone.position.y = dir * (r + beamLen / 2);
    if (dir < 0) cone.rotation.x = Math.PI; // flip the lower beam to point down
    group.add(cone);
  }
  beacons.push({ material });
  return group;
}

function makeBlackHole(node) {
  const r = MIN_PLANET_R + clamp01(Number(node.size_scale) || 0) * 0.9;
  const hole = new THREE.Mesh(
    new THREE.SphereGeometry(r, 28, 28),
    new THREE.MeshBasicMaterial({ color: 0x000000 }),
  );
  hole.add(makeBlackHoleBeacon(r));
  blackHoles.push({ mesh: hole, radius: r });
  return hole;
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

// A flat ring whose UVs are remapped radially (u = 0 at the inner edge → 1 at the
// outer) so a 1-D gradient texture's bands follow the radius. Used by the Saturn ring.
function radialRingGeometry(inner, outer, segments) {
  const geo = new THREE.RingGeometry(inner, outer, segments, 4);
  const pos = geo.attributes.position;
  const uv = geo.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    const d = Math.hypot(pos.getX(i), pos.getY(i));
    uv.setXY(i, (d - inner) / (outer - inner), 0.5);
  }
  uv.needsUpdate = true;
  return geo;
}

function makeRing(planetR) {
  // Radially-mapped so the ring texture's bands + Cassini gap follow the radius.
  const ring = new THREE.Mesh(
    radialRingGeometry(planetR * 1.35, planetR * 2.35, 128),
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
// Unfocused connections keep their steady grey trajectory line as the main
// element; a subtle cool "electron" glides back and forth along it — each edge
// with its own phase/speed/direction so the web shimmers gently, without a
// synchronised pulse or a blooming spark.
const FLOW_BASE = new THREE.Color(0x6b7280); // the steady grey trajectory line
const ELECTRON_COOL = new THREE.Color(0x828fa0); // travelling electron body (muted cool)
const ELECTRON_HOT = new THREE.Color(0xa6b2c2); // electron core (faint cool highlight)
const FLOW_SPEED = 0.1; // base electron round-trips/sec (slow, calm drift)
const FLOW_WIDTH = 0.12; // Gaussian half-width of the electron along the link
const FLOW_CREST = 0.32; // mild brightening at the electron core (kept subtle)
const _pulse = new THREE.Color();
const edgeFlow = []; // per-edge { phase, speed, dir } for the idle electron flow
let linkMesh = null;
let linkPositions = null;
let linkColors = null;

function buildLinks() {
  if (edges.length === 0) return;
  const flowRand = mulberry32(0xe1ec);
  for (let i = 0; i < edges.length; i++) {
    edgeFlow.push({
      phase: flowRand(),
      speed: 0.7 + flowRand() * 0.8,
      dir: flowRand() < 0.5 ? -1 : 1,
    });
  }
  const verts = edges.length * SEG_PER_EDGE * 2;
  linkPositions = new Float32Array(verts * 3);
  linkColors = new Float32Array(verts * 3);
  for (let v = 0; v < verts; v++) FLOW_BASE.toArray(linkColors, v * 3);
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(linkPositions, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(linkColors, 3));
  linkMesh = new THREE.LineSegments(
    geo,
    new THREE.LineBasicMaterial({
      vertexColors: true,
      transparent: true,
      opacity: 0.3,
      depthWrite: false,
    }),
  );
  systemGroup.add(linkMesh);
}
buildLinks();

// How high each link bows off its straight midpoint, as a fraction of the link's
// length — a gentle upward arc so spokes read as orbits, not taut strings.
const LINK_ARC_HEIGHT = 0.12;
const _a = new THREE.Vector3();
const _b = new THREE.Vector3();
const _ctrl = new THREE.Vector3();
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
    // Bodies settle after the force layout, so a link is a fixed arc: start from
    // the midpoint and lift the Bézier control point to bow each spoke gently up.
    _ctrl.addVectors(_a, _b).multiplyScalar(0.5);
    _ctrl.y += _a.distanceTo(_b) * LINK_ARC_HEIGHT;
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

// Paint every link each frame: the focused chain flows the red "Petrova line"
// pulse, a hovered chain stays static crimson, other edges dim while a planet is
// focused, and — in the default view — each link carries a lone electron
// drifting back and forth along a faint track.
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
    if (hoverChain && hoverChain.has(i)) {
      for (let v = 0; v < perEdge; v++) PETROVA_HOVER.toArray(linkColors, base + v * 3);
      continue;
    }
    if (focusChain) {
      for (let v = 0; v < perEdge; v++) LINE_DIM.toArray(linkColors, base + v * 3);
      continue;
    }
    const flow = edgeFlow[i];
    for (let seg = 0; seg < SEG_PER_EDGE; seg++) {
      writeElectron(base + seg * 6, seg / SEG_PER_EDGE, elapsed, flow);
      writeElectron(base + seg * 6 + 3, (seg + 1) / SEG_PER_EDGE, elapsed, flow);
    }
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

// Colour one link vertex for the idle flow: the steady grey line plus a gentle
// Gaussian electron whose centre rides a triangle wave 0→1→0 (so it flows out
// and back), offset per edge by its phase/speed/direction.
function writeElectron(offset, s, elapsed, flow) {
  const cycles = flow.phase + flow.dir * elapsed * FLOW_SPEED * flow.speed;
  const frac = cycles - Math.floor(cycles);
  const tri = 1 - Math.abs(2 * frac - 1); // 0 → 1 → 0 along the link
  const d = s - tri;
  const spark = Math.exp(-(d * d) / (2 * FLOW_WIDTH * FLOW_WIDTH));
  _pulse
    .copy(FLOW_BASE)
    .lerp(ELECTRON_COOL, spark)
    .lerp(ELECTRON_HOT, spark * spark)
    .multiplyScalar(1 + FLOW_CREST * spark * spark);
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
      showTooltip(hovered.userData.node);
    } else {
      hoverChain = null;
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
  lensPass.uniforms.resolution.value.set(w, h);
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
  paintLinks(elapsed);
  if (focusChain && focusHalo) {
    focusHalo.material.opacity = 0.55 + 0.3 * Math.sin(elapsed * PULSE_SPEED);
  }
  if (beacons.length) {
    const beaconOpacity = BEACON_OPACITY + 0.12 * Math.sin(elapsed * BEACON_PULSE_SPEED);
    for (const b of beacons) b.material.opacity = beaconOpacity;
  }
  updateLensUniforms();
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
