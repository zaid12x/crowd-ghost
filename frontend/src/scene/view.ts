import * as THREE from 'three';
import { HeatField } from './heat';
import { AgentField } from './agents';
import { buildMuseum, GeometryPayload } from './museum';
import { AsciiPass, GhostMode } from './postprocess';

export interface PaneFrame {
  tick: number;
  agents: Float32Array;
  nAgents: number;
  rooms: Float32Array;
  nRooms: number;
}

/** One self-contained museum view: own renderer, scene, camera, agents, ASCII pass. */
export class GhostPane {
  private renderer: THREE.WebGLRenderer;
  private scene: THREE.Scene;
  private persp: THREE.PerspectiveCamera;
  private ortho: THREE.OrthographicCamera;
  private agents: AgentField;
  private heat: HeatField;
  private ascii: AsciiPass | null;
  private museum: ReturnType<typeof buildMuseum> | null = null;
  private bounds: [number, number] = [40, 30];
  readonly withAscii: boolean;
  readonly captionEl: HTMLDivElement;
  mode: GhostMode = 'ghost';
  onFps: ((fps: number) => void) | null = null;

  constructor(container: HTMLElement, opts: { withAscii: boolean; caption: string }) {
    this.withAscii = opts.withAscii;
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor(0x050805, 1);
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%';
    container.appendChild(renderer.domElement);
    this.renderer = renderer;

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(0x050805, 95, 180);

    this.persp = new THREE.PerspectiveCamera(52, 1, 0.1, 200);
    this.ortho = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 200);

    this.agents = new AgentField();
    this.scene.add(this.agents.group);
    this.heat = new HeatField(40, 30);
    this.ascii = opts.withAscii ? new AsciiPass() : null;

    this.captionEl = document.createElement('div');
    this.captionEl.textContent = `[ ${opts.caption} ]`;
    this.captionEl.style.cssText =
      'position:absolute;top:10px;left:50%;transform:translateX(-50%);font-family:"IBM Plex Mono","Courier New",monospace;' +
      'font-size:9px;letter-spacing:3px;color:#ffb000;opacity:0.9;pointer-events:none;text-shadow:0 0 8px rgba(255,176,0,0.4);' +
      'padding:2px 10px;border-top:1px solid #2e332a;border-bottom:1px solid #2e332a;background:rgba(10,10,10,0.55)';
    container.appendChild(this.captionEl);
  }

  setGeometry(geo: GeometryPayload) {
    if (this.museum) {
      this.scene.remove(this.museum.group);
    }
    this.bounds = geo.bounds;
    this.heat = new HeatField(geo.bounds[0], geo.bounds[1]);
    this.museum = buildMuseum(geo, this.scene);
    this.scene.remove(this.agents.group);
    this.scene.add(this.agents.group);
    this.layout();
    this.applyMode(this.mode);
  }

  setBoundsFallback(bounds: [number, number]) {
    this.bounds = bounds;
    this.layout();
  }

  private layout() {
    const [W, H] = this.bounds;
    const aspect = this.renderer.domElement.clientWidth / Math.max(1, this.renderer.domElement.clientHeight);
    const fit = Math.min(Math.max(aspect, 0.9), 1.35);
    const dist = (W / 2 + 5) / (Math.tan((52 * Math.PI / 180) / 2) * fit);
    const elev = 1.02;
    this.persp.position.set(W / 2, dist * Math.sin(elev), H / 2 + dist * Math.cos(elev));
    this.persp.lookAt(W / 2, 0, H / 2);
    this.persp.fov = 52;
    this.persp.aspect = aspect;
    this.persp.updateProjectionMatrix();

    const margin = 2.2;
    const halfW = (W + margin) / 2;
    const halfH = (H + margin) / 2;
    const w = Math.max(halfW, halfH * aspect);
    const h = w / aspect;
    this.ortho.left = -w; this.ortho.right = w; this.ortho.top = h; this.ortho.bottom = -h;
    this.ortho.position.set(W / 2, 60, H / 2);
    this.ortho.lookAt(W / 2, 0, H / 2);
    this.ortho.updateProjectionMatrix();

    this.renderer.setSize(this.renderer.domElement.clientWidth, this.renderer.domElement.clientHeight, false);
    if (this.ascii) {
      const size = this.renderer.getDrawingBufferSize(new THREE.Vector2());
      this.ascii.resize(size.x, size.y);
    }
  }

  resize() {
    const el = this.renderer.domElement;
    this.renderer.setSize(el.clientWidth, el.clientHeight, false);
    this.layout();
  }

  applyMode(next: GhostMode) {
    this.mode = next;
    if (!this.museum) return;
    const { group, wallSolids, strokes, floors } = this.museum;
    if (next === 'ghost') {
      group.visible = true; wallSolids.visible = true; floors.visible = true; strokes.visible = false;
    } else if (next === 'xray') {
      group.visible = false; strokes.visible = false;
    } else {
      group.visible = true; wallSolids.visible = false; floors.visible = false; strokes.visible = true;
    }
  }

  update(f: PaneFrame) {
    this.heat.update(f.agents, f.nAgents);
    this.agents.update(f.agents, f.nAgents, (x: number, y: number) => this.heat.sample(x, y));
  }

  render(timeMs: number) {
    // self-heal canvas size
    const c = this.renderer.domElement;
    const pr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.floor(c.clientWidth * pr);
    const h = Math.floor(c.clientHeight * pr);
    if (c.width !== w || c.height !== h) {
      this.renderer.setPixelRatio(pr);
      this.renderer.setSize(c.clientWidth, c.clientHeight, false);
      this.layout();
    }
    this.renderer.setRenderTarget(null);
    if (this.mode === 'blueprint' || !this.ascii) {
      this.renderer.setClearColor(0x050805, 1);
      this.renderer.render(this.scene, this.mode === 'blueprint' ? this.ortho : this.persp);
      return;
    }
    this.ascii.setHeat(this.heat.texture, this.heat.max);
    this.ascii.render(this.renderer, this.scene, this.persp, this.mode, timeMs);
  }
}
