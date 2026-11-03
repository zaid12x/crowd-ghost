import * as THREE from 'three';
import { GhostSocket, Frame } from './net/ws';
import { HeatField } from './scene/heat';
import { AgentField } from './scene/agents';
import { buildMuseum, GeometryPayload } from './scene/museum';
import { AsciiPass, GhostMode } from './scene/postprocess';

const app = document.getElementById('app')!;
const hud = document.getElementById('hud')!;
const hudMode = document.createElement('div');
hudMode.id = 'modebar';
hudMode.innerHTML = `
  <button data-mode="ghost" class="active">1 GHOST</button>
  <button data-mode="xray">2 X-RAY</button>
  <button data-mode="blueprint">3 BLUEPRINT</button>`;
document.body.appendChild(hudMode);

const style = document.createElement('style');
style.textContent = `
  #hud { top: 14px !important; left: 16px !important; font-size: 11px !important; line-height: 1.55 !important; z-index: 5; }
  #modebar { position: fixed; bottom: 16px; right: 18px; z-index: 6; display: flex; gap: 8px; }
  #modebar button {
    font-family: 'IBM Plex Mono', 'Courier New', monospace; font-size: 11px; letter-spacing: 1px;
    background: rgba(4, 12, 6, 0.75); color: #39ff14; border: 1px solid #1f4a2a;
    padding: 8px 12px; cursor: pointer; text-shadow: 0 0 6px #39ff14;
  }
  #modebar button.active { background: #0e2f16; border-color: #39ff14; box-shadow: 0 0 14px rgba(57,255,20,0.35); }
  #modebar button:hover { background: #0e2f16; }
`;
document.head.appendChild(style);

// ---------- renderer / scene ----------
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.setClearColor(0x050805, 1);
app.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x050805, 95, 180);

const persp = new THREE.PerspectiveCamera(50, innerWidth / innerHeight, 0.1, 200);
const ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 200);

const agents = new AgentField();
scene.add(agents.group);

const heat = new HeatField(40, 30);
const ascii = new AsciiPass();

let museum: ReturnType<typeof buildMuseum> | null = null;
let roomNames: string[] = [];
let bounds: [number, number] = [40, 30];
let mode: GhostMode = 'ghost';
let lastFrame: Frame | null = null;

function applyMode(next: GhostMode) {
  mode = next;
  document.querySelectorAll('#modebar button').forEach((b) =>
    b.classList.toggle('active', (b as HTMLButtonElement).dataset.mode === next)
  );
  if (!museum) return;
  const { group, wallSolids, strokes, floors } = museum;
  if (next === 'ghost') {
    group.visible = true;
    wallSolids.visible = true;
    floors.visible = true;
    strokes.visible = false;
  } else if (next === 'xray') {
    group.visible = false; // nothing but the ghosts + heat glow
    strokes.visible = false;
  } else {
    // blueprint: top-down line strokes only
    group.visible = true;
    wallSolids.visible = false;
    floors.visible = false;
    strokes.visible = true;
  }
}

function layoutWorld() {
  const [W, H] = bounds;
  const aspect = innerWidth / innerHeight;
  const fit = Math.min(Math.max(aspect, 0.9), 1.35); // landscape: fit height, not width
  const dist = (W / 2 + 5) / (Math.tan((52 * Math.PI / 180) / 2) * fit);
  const elev = 1.02; // ~58°
  persp.position.set(W / 2, dist * Math.sin(elev), H / 2 + dist * Math.cos(elev));
  persp.lookAt(W / 2, 0, H / 2);
  persp.fov = 52;
  persp.aspect = aspect;
  persp.updateProjectionMatrix();
  const margin = 2.2;
  const halfW = (W + margin) / 2;
  const halfH = (H + margin) / 2;
  const w = Math.max(halfW, halfH * aspect);
  const h = w / aspect;
  ortho.left = -w; ortho.right = w; ortho.top = h; ortho.bottom = -h;
  ortho.position.set(W / 2, 60, H / 2);
  ortho.lookAt(W / 2, 0, H / 2);
  ortho.updateProjectionMatrix();
}

async function boot() {
  try {
    const [health, geometry] = await Promise.all([
      fetch('/api/health').then((r) => r.json()),
      fetch('/api/geometry').then((r) => r.json()),
    ]);
    bounds = (health.bounds ?? geometry.bounds) as [number, number];
    roomNames = (geometry as GeometryPayload).rooms.map((r) => r.name.toUpperCase());
    const built = buildMuseum(geometry as GeometryPayload, scene);
    museum = built;
    scene.remove(agents.group);
    scene.add(agents.group); // keep rendering order simple: agents on top
    applyMode(mode);
    layoutWorld();
    const activeCamera = mode === 'blueprint' ? ortho : persp;
    void activeCamera;
  } catch (e) {
    console.error('boot failed', e);
  }
}
void boot();

// ---------- net ----------
const socket = new GhostSocket();
let fps = 60;
let lastT = performance.now();
socket.onStatus = (s) => { hud.textContent = `CROWD GHOST\n${s}`; };
socket.onFrame = (f) => {
  lastFrame = f;
  heat.update(f.agents, f.nAgents);
  agents.update(f.agents, f.nAgents, (x, y) => heat.sample(x, y));
  const now = performance.now();
  const dt = now - lastT;
  lastT = now;
  fps = fps * 0.92 + (1000 / Math.max(dt, 1e-3)) * 0.08;
  const roomLines = Array.from({ length: Math.min(f.nRooms, 4) }, (_, i) => {
    const rho = f.rooms[i * 3 + 1];
    const q = f.rooms[i * 3];
    const rname = roomNames[i] ?? `ROOM${i}`;
    return `${rname}  rho ${rho.toFixed(2)}  q ${q.toFixed(0)}`;
  });
  hud.textContent = [`CROWD GHOST — ${roomNames.length ? 'LIVE' : ''}`, `TICK ${f.tick}  FPS ${fps.toFixed(0)}`, `AGENTS ${f.nAgents}`, ...roomLines].join('\n');
};
socket.connect();
(window as unknown as { __ghost: unknown }).__ghost = { camera: persp, renderer, scene, ascii, ortho };

// ---------- resize ----------
addEventListener('resize', () => {
  renderer.setSize(innerWidth, innerHeight);
  layoutWorld();
  const size = renderer.getDrawingBufferSize(new THREE.Vector2());
  ascii.resize(size.x, size.y);
});

// ---------- mode switching ----------
document.querySelectorAll('#modebar button').forEach((b) => {
  b.addEventListener('click', () => applyMode((b as HTMLButtonElement).dataset.mode as GhostMode));
});
addEventListener('keydown', (e) => {
  if (e.key === '1') applyMode('ghost');
  else if (e.key === '2') applyMode('xray');
  else if (e.key === '3') applyMode('blueprint');
});

// ---------- render loop ----------
renderer.setAnimationLoop((timeMs) => {
  const c = renderer.domElement;
  const pr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.floor(c.clientWidth * pr);
  const h = Math.floor(c.clientHeight * pr);
  if (c.width !== w || c.height !== h) {
    renderer.setPixelRatio(pr);
    renderer.setSize(c.clientWidth, c.clientHeight, false);
    layoutWorld();
  }

  ascii.setHeat(heat.texture, heat.max);
  if (mode === 'blueprint') {
    renderer.setRenderTarget(null);
    renderer.setClearColor(0x050805, 1);
    renderer.render(scene, ortho);
  } else {
    ascii.render(renderer, scene, persp, mode, timeMs);
  }
});
