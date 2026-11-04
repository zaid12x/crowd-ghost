import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import '@fontsource/ibm-plex-mono/700.css';
import '@fontsource/vt323/400.css';
import './ui/hud.css';

import { GhostSocket, Frame } from './net/ws';
import { GhostPane } from './scene/view';
import { GeometryPayload } from './scene/museum';
import { HudTelemetry } from './ui/hud';
import { CrowdPressureDial } from './ui/dial';

// ---------- DOM skeleton ----------
const root = document.body;
const el = document.createElement('div');
el.innerHTML = `
  <header id="placard">
    <div class="cg-mark">
      <svg class="cg-ghost" viewBox="0 0 32 40" width="22" height="28" aria-hidden="true">
        <path d="M16 2C8.6 2 4.6 9.2 4.6 17v19l5.7-4.8L16 36l5.7-4.8L27.4 36V17C27.4 9.2 23.4 2 16 2z" fill="#4af626"/>
        <circle cx="11.6" cy="17.2" r="1.9" fill="#0a0a0a"/>
        <circle cx="20.4" cy="17.2" r="1.9" fill="#0a0a0a"/>
      </svg>
      <div>
        <div class="cg-word">CROWD GHOST</div>
        <div class="cg-sub">Every crowd leaves a ghost. Fix it.</div>
      </div>
    </div>
    <div class="placard-center">HALL OF <span class="hall" id="placardHall">THE BOTTLENECK</span></div>
    <div class="placard-meta"><span>CAT. <b>CG-04</b></span><span id="placardFps"><span class="dot"></span>60 FPS</span></div>
  </header>

  <main id="stage">
    <div id="leftRail">
      <div id="telemetry"></div>
      <div id="pressureWrap"></div>
    </div>
    <div id="canvasWrap">
      <div id="paneA"></div>
      <div id="paneB"></div>
      <span class="pane-crosshair" style="top:8px;left:10px">+</span>
      <span class="pane-crosshair" style="top:8px;right:10px">+</span>
      <span class="pane-crosshair" style="bottom:8px;left:10px">+</span>
      <span class="pane-crosshair" style="bottom:8px;right:10px">+</span>
      <aside id="curator" class="plate">
        <div class="plate-title"><span>// CURATOR — MUSEUM OS</span><em>v1.3</em></div>
        <div id="curatorBody"><div class="line-ok">BOOT SEQUENCE…</div></div>
        <div class="curator-foot"><span>DETERMINISTIC · MODEL-TRACEABLE</span><button class="ghostbtn" id="whyBtn">WHY?</button></div>
      </aside>
      <div id="modebar">
        <button class="mode-btn active" data-mode="ghost">1 GHOST<small>ISO→ASCII</small></button>
        <button class="mode-btn" data-mode="xray">2 X-RAY<small>HEAT ONLY</small></button>
        <button class="mode-btn" data-mode="blueprint">3 PLAN<small>TOP-DOWN</small></button>
        <button class="mode-btn" id="splitBtn">4 SPLIT<small>A/B TEST</small></button>
        <button class="mode-btn" id="curatorBtn">5 CURATOR<small>MUSEUM OS</small></button>
      </div>
    </div>
    <div id="rightRail">
      <aside id="panel" class="plate">
        <div class="plate-title"><span>// SERVICE PANEL</span><em id="panelReset" style="cursor:pointer;color:var(--amber)">RESET</em></div>
        <div id="panelBody">
          <label for="levelSelect">HALL / LEVEL</label>
          <select id="levelSelect">
            <option value="bottleneck">THE BOTTLENECK</option>
            <option value="lobby">VERNISSAGE — FULL HOUSE</option>
            <option value="rush">THE RUSH — OPENING NIGHT</option>
            <option value="firedrill">FIRE DRILL — EVACUATION</option>
          </select>
          <label for="gammaScale">ENTRY RATE <span class="val" id="gammaVal">100%</span></label>
          <input id="gammaScale" type="range" min="0.2" max="1.5" step="0.05" value="1.0">
          <div id="capSliders"></div>
          <div id="doorSliders"></div>
        </div>
        <div class="panel-foot">Left pane only — right pane keeps the optimized layout</div>
      </aside>
    </div>
  </main>

  <footer id="statusbar">
    <span><b>CROWD GHOST</b> v1.0</span>
    <span>CURATOR v1.3 — <b>NO LLM, EVERY CLAIM HAS A NUMBER</b></span>
    <span>MODEL: JACKSON NETWORK + ERLANG C</span>
    <span class="warn">HOLD RHO &lt; 0.85 OR THE QUEUE FEEDS ITSELF</span>
    <span>EXIT FLOW ONLY: LOBBY → GALLERY → SHOP</span>
  </footer>

  <div id="whyOverlay"><pre id="whyGraph"></pre><button class="ghostbtn" id="whyClose">CLOSE</button></div>
  <div id="scanlines"></div>
  <div id="grain"></div>`;
root.appendChild(el);

const stage = document.getElementById('stage')!;
const paneAEl = document.getElementById('paneA')!;
const paneBEl = document.getElementById('paneB')!;
const curatorEl = document.getElementById('curator')!;
const curatorBody = document.getElementById('curatorBody')!;

// ---------- views ----------
const paneA = new GhostPane(paneAEl, { withAscii: true, caption: 'CURRENT LAYOUT' });
let paneB: GhostPane | null = null;
let geometry: GeometryPayload | null = null;
let levelName = '';
let splitOn = false;
let fps = 60;
let sideBAgents = 0;
let currentMode: 'ghost' | 'xray' | 'blueprint' = 'ghost';

const telemetry = new HudTelemetry();
document.getElementById('telemetry')!.appendChild(telemetry.el);
const dial = new CrowdPressureDial();
document.getElementById('pressureWrap')!.appendChild(dial.el);

async function boot() {
  try {
    const [health, geometryPayload] = await Promise.all([
      fetch('/api/health').then((r) => r.json()),
      fetch('/api/geometry').then((r) => r.json()),
    ]);
    geometry = geometryPayload as GeometryPayload;
    levelName = (health.name ?? 'THE MUSEUM').toUpperCase();
    document.getElementById('placardHall')!.textContent = levelName;
    paneA.setGeometry(geometry);
    telemetry.setRooms(geometry.rooms.map((r) => r.name.toUpperCase()));
    buildSliders(health);
    paneB = new GhostPane(paneBEl, { withAscii: false, caption: 'OPTIMIZED' });
    paneB.setGeometry(geometry);
    applyMode(currentMode);
    // Reflect a server-side split (e.g. after a reload) instead of leaving the
    // pane hidden while side-B frames stream to nobody.
    if (health.split) {
      splitOn = true;
      document.body.classList.add('split');
      document.getElementById('splitBtn')!.classList.add('active');
      setTimeout(() => { paneA.resize(); paneB?.resize(); }, 150);
    }
  } catch (e) {
    console.error('boot failed', e);
  }
}

// ---------- sliders ----------
const capContainer = document.getElementById('capSliders')!;
const doorContainer = document.getElementById('doorSliders')!;
let capacities: number[] = [];
let doorWidths: Record<string, number> = {};
let debounce: ReturnType<typeof setTimeout> | null = null;
// The embedded browser restores stale form values across reloads and fires
// input/change for them. For the first seconds after boot those events are
// echoes, not user intent — dropping them keeps the server on its defaults.
const bootTime = performance.now();

function buildSliders(health: { gamma?: number; capacities?: number[]; door_widths?: Record<string, number>; level?: string }) {
  capacities = (health.capacities ?? []).slice();
  doorWidths = { ...(health.door_widths ?? {}) };
  const levelSelect = document.getElementById('levelSelect') as HTMLSelectElement;
  if (health.level && levelSelect) levelSelect.value = health.level;

  capContainer.innerHTML =
    '<label>ROOM CAPACITIES</label>' +
    capacities.map((c, i) => `
    <label for="capSlider${i}">${(geometry?.rooms[i]?.name ?? 'ROOM ' + i).toUpperCase()} <span class="val" id="capVal${i}">${c}</span></label>
    <input type="range" id="capSlider${i}" class="capSlider" data-i="${i}" min="1" max="120" step="1" value="${c}">`).join('');
  doorContainer.innerHTML =
    '<label>DOOR WIDTHS (m)</label>' +
    Object.entries(doorWidths).slice(0, 6).map(([id, w]) => `
    <label for="doorSlider_${id}">${id.toUpperCase().replace(/_/g, ' ')} <span class="val" id="doorVal_${id}">${w.toFixed(1)}</span></label>
    <input type="range" id="doorSlider_${id}" class="doorSlider" data-id="${id}" min="1.0" max="4.0" step="0.1" value="${w}">`).join('');

  capContainer.querySelectorAll<HTMLInputElement>('.capSlider').forEach((el) => {
    el.addEventListener('input', () => {
      const i = Number(el.dataset.i);
      capacities[i] = Number(el.value);
      document.getElementById(`capVal${i}`)!.textContent = el.value;
      scheduleParams();
    });
  });
  doorContainer.querySelectorAll<HTMLInputElement>('.doorSlider').forEach((el) => {
    el.addEventListener('input', () => {
      const id = el.dataset.id!;
      doorWidths[id] = Number(el.value);
      document.getElementById(`doorVal_${id}`)!.textContent = Number(el.value).toFixed(1);
      scheduleParams();
    });
  });
}

function sendParams() {
  const gammaScale = Number((document.getElementById('gammaScale') as HTMLInputElement).value);
  socket.send({ type: 'params', gamma_scale: gammaScale, capacities: capacities.slice(), door_widths: { ...doorWidths } });
}
function scheduleParams() {
  if (performance.now() - bootTime < 2500) return; // ignore restore echoes right after boot
  if (debounce) clearTimeout(debounce);
  debounce = setTimeout(sendParams, 120);
}
document.getElementById('gammaScale')!.addEventListener('input', (e) => {
  (document.getElementById('gammaVal')!).textContent = `${Math.round(Number((e.target as HTMLInputElement).value) * 100)}%`;
  scheduleParams();
});
document.getElementById('panelReset')!.addEventListener('click', () => {
  (document.getElementById('gammaScale') as HTMLInputElement).value = '1.0';
  document.getElementById('gammaVal')!.textContent = '100%';
  fetch('/api/health').then((r) => r.json()).then(buildSliders).then(sendParams);
});
document.getElementById('levelSelect')!.addEventListener('change', (e) => {
  socket.send({ type: 'level', id: (e.target as HTMLSelectElement).value });
});

// ---------- net ----------
const socket = new GhostSocket();
let lastT = performance.now();
socket.onStatus = () => { /* status surfaced via placard FPS dot; stay terse */ };
socket.onFrame = (f: Frame) => {
  const sideB = (f.flags & 2) !== 0;
  if (sideB) {
    sideBAgents = f.nAgents;
    paneB?.update(f);
    telemetry.updateSideB(f);
    return;
  }
  paneA.update(f);
  const now = performance.now();
  const dt = now - lastT;
  lastT = now;
  fps = fps * 0.92 + (1000 / Math.max(dt, 1e-3)) * 0.08;

  telemetry.update(f, levelName, fps, splitOn, sideBAgents);
  let maxRho = 0;
  for (let i = 0; i < f.nRooms; i++) maxRho = Math.max(maxRho, f.rooms[i * 3 + 1]);
  dial.setRho(maxRho);

  const fpsEl = document.getElementById('placardFps');
  if (fpsEl && (f.tick & 7) === 0) fpsEl.innerHTML = `<span class="dot"></span>${Math.round(fps)} FPS · T${f.tick}`;
};
socket.connect();
(window as unknown as { __ghost: unknown }).__ghost = { paneA, get paneB() { return paneB; }, telemetry, dial };

// ---------- modes ----------
const modeBar = document.getElementById('modebar')!;
function applyMode(next: typeof currentMode) {
  currentMode = next;
  paneA.applyMode(next);
  paneB?.applyMode(next);
  modeBar.querySelectorAll('button[data-mode]').forEach((b) =>
    b.classList.toggle('active', (b as HTMLButtonElement).dataset.mode === next)
  );
}
modeBar.querySelectorAll('button[data-mode]').forEach((b) =>
  b.addEventListener('click', () => applyMode((b as HTMLButtonElement).dataset.mode as typeof currentMode))
);

// ---------- split ----------
const splitBtn = document.getElementById('splitBtn')!;
function toggleSplit() {
  splitOn = !splitOn;
  document.body.classList.toggle('split', splitOn);
  splitBtn.classList.toggle('active', splitOn);
  socket.send({ type: 'split', on: splitOn });
  [150, 450].forEach((ms) => setTimeout(() => { paneA.resize(); paneB?.resize(); }, ms));
}
splitBtn.addEventListener('click', toggleSplit);

// ---------- curator ----------
const curatorBtn = document.getElementById('curatorBtn')!;
let curatorOn = false;
function toggleCurator() {
  curatorOn = !curatorOn;
  curatorEl.style.display = curatorOn ? 'block' : 'none';
  curatorBtn.classList.toggle('active', curatorOn);
  if (curatorOn) refreshCurator();
}
curatorBtn.addEventListener('click', toggleCurator);

async function refreshCurator() {
  try {
    const c = await fetch('/api/curator').then((r) => r.json());
    curatorBody.innerHTML = c.lines.map((l: { severity: string; text: string }) =>
      `<div class="line-${l.severity}">${l.text}</div>`).join('');
    (document.getElementById('whyGraph')!).textContent = c.graph;
  } catch {
    curatorBody.innerHTML = '<div class="line-alert">CURATOR OFFLINE — MODEL UNREACHABLE</div>';
  }
}
setInterval(() => { if (curatorOn) refreshCurator(); }, 2000);
document.getElementById('whyBtn')!.addEventListener('click', () => { document.getElementById('whyOverlay')!.style.display = 'flex'; });
document.getElementById('whyClose')!.addEventListener('click', () => { document.getElementById('whyOverlay')!.style.display = 'none'; });

addEventListener('keydown', (e) => {
  // Ignore key echoes replayed by the browser right after boot (same quirk
  // as the restored slider values).
  if (performance.now() - bootTime < 2500) return;
  if (e.key === '1') applyMode('ghost');
  else if (e.key === '2') applyMode('xray');
  else if (e.key === '3') applyMode('blueprint');
  else if (e.key === '4') toggleSplit();
  else if (e.key === '5') toggleCurator();
  else if (e.key === 'Escape') document.getElementById('whyOverlay')!.style.display = 'none';
});

addEventListener('resize', () => { paneA.resize(); paneB?.resize(); });

boot().then(() => {
  const loop = (timeMs: number) => {
    paneA.render(timeMs);
    if (splitOn && paneB) paneB.render(timeMs);
    requestAnimationFrame(loop);
  };
  requestAnimationFrame(loop);
});
