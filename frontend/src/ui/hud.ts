/**
 * TICKET STUB — gallery flow telemetry. One row per room: rho bar cells,
 * Wq, queue length. Overload rows burn hazard red; the banner trips at rho>0.85.
 */

export interface HudFrame {
  tick: number;
  agents: Float32Array;
  nAgents: number;
  rooms: Float32Array;
  nRooms: number;
}

const LOAD_CELLS = 8;

export class HudTelemetry {
  readonly el: HTMLDivElement;
  private levelEl: HTMLDivElement;
  private tickEl: HTMLSpanElement;
  private agentsEl: HTMLDivElement;
  private fpsEl: HTMLDivElement;
  private rowsWrap: HTMLDivElement;
  private banner: HTMLDivElement;
  private rowEls: HTMLDivElement[] = [];
  private roomNames: string[] = [];

  private sideBEl: HTMLDivElement;
  private sideBText: HTMLSpanElement;
  private sideB = { maxRho: 0, totalQueue: 0, nAgents: 0 };

  constructor() {
    const el = document.createElement('div');
    el.className = 'telemetry-plate';
    el.innerHTML = `
      <div class="plate-title"><span>// GALLERY FLOW &mdash; TICKET STUB</span><em id="tkFps">60 FPS</em></div>
      <div class="tk-meta"><span id="tkLevel">—</span><span id="tkAgents">AGENTS 0</span></div>
      <div class="tk-row tk-header"><span>ROOM</span><span>RHO</span><span>Wq</span><span>QUEUE</span><span>LOAD</span></div>
      <div id="tkRows"></div>
      <div id="tkSideB" class="tk-sideb"><span class="tk-sideb-label">OPTIMIZED (B)</span><span id="tkSideBText">—</span></div>
      <div id="tkBanner" class="tk-banner"><span class="tk-stripe">OVERLOAD</span><span id="tkBannerText" class="tk-banner-text"></span></div>`;
    this.el = el;
    this.levelEl = el.querySelector('#tkLevel')!;
    this.tickEl = document.createElement('span');
    this.agentsEl = el.querySelector('#tkAgents')!;
    this.fpsEl = el.querySelector('#tkFps')!;
    this.rowsWrap = el.querySelector('#tkRows')!;
    this.banner = el.querySelector('#tkBanner')!;
    this.sideBEl = el.querySelector('#tkSideB')!;
    this.sideBText = el.querySelector('#tkSideBText')!;
  }

  setRooms(names: string[]) {
    this.roomNames = names;
    this.rowsWrap.innerHTML = names.map((name) => `
      <div class="tk-row" data-room>
        <span class="tk-name">${name}</span>
        <span class="tk-rho">0.00</span>
        <span class="tk-wq">0.0s</span>
        <span class="tk-q">0</span>
        <span class="tk-load">${Array.from({ length: LOAD_CELLS }, () => '<i></i>').join('')}</span>
      </div>`).join('');
    this.rowEls = Array.from(this.rowsWrap.querySelectorAll<HTMLDivElement>('[data-room]'));
  }

  /** Aggregate the latest side-B (optimized) frame. */
  updateSideB(f: HudFrame) {
    let maxRho = 0, totalQueue = 0;
    for (let i = 0; i < f.nRooms; i++) {
      maxRho = Math.max(maxRho, f.rooms[i * 3 + 1]);
      totalQueue += f.rooms[i * 3];
    }
    this.sideB = { maxRho, totalQueue, nAgents: f.nAgents };
  }

  private renderSideB(splitOn: boolean) {
    this.sideBEl.classList.toggle('show', splitOn);
    if (!splitOn) return;
    const { maxRho, totalQueue, nAgents } = this.sideB;
    const hot = maxRho > 0.85;
    this.sideBText.textContent = `AGENTS ${nAgents} · WORST RHO ${maxRho.toFixed(2)} · QUEUED ${Math.round(totalQueue)}${hot ? ' · HOT' : ''}`;
    this.sideBText.classList.toggle('hot', hot);
  }

  update(f: HudFrame, levelName: string, fps: number, splitOn: boolean, sideBAgents: number) {
    this.levelEl.textContent = (levelName || 'UNKNOWN HALL').toUpperCase();
    this.fpsEl.textContent = `${Math.round(fps)} FPS · TICK ${f.tick}`;
    this.agentsEl.textContent = splitOn ? `AGENTS ${f.nAgents} ⇄ ${sideBAgents}` : `AGENTS ${f.nAgents}`;
    this.renderSideB(splitOn);

    let worst = 0, worstName = '';
    for (let i = 0; i < Math.min(f.nRooms, this.rowEls.length); i++) {
      const rho = f.rooms[i * 3 + 1];
      const q = f.rooms[i * 3];
      const wq = f.rooms[i * 3 + 2];
      if (rho > worst) { worst = rho; worstName = this.roomNames[i] ?? `ROOM ${i}`; }
      const row = this.rowEls[i];
      row.classList.toggle('hot', rho > 0.85);
      row.classList.toggle('warm', rho > 0.6 && rho <= 0.85);
      row.querySelector('.tk-rho')!.textContent = rho.toFixed(2);
      row.querySelector('.tk-wq')!.textContent = wq >= 999 ? '—' : `${wq.toFixed(1)}s`;
      row.querySelector('.tk-q')!.textContent = String(Math.round(q)).padStart(2, '0');
      const cells = row.querySelectorAll<HTMLElement>('.tk-load i');
      const filled = Math.round(Math.min(1, rho) * LOAD_CELLS);
      cells.forEach((c, j) => {
        c.classList.toggle('on', j < filled);
        c.classList.toggle('hot', j < filled && rho > 0.85);
        c.classList.toggle('warm', j < filled && rho > 0.6 && rho <= 0.85);
      });
    }

    if (worst > 0.85) {
      this.banner.classList.add('show');
      this.banner.querySelector('#tkBannerText')!.textContent =
        `${worstName.toUpperCase()} RHO ${worst.toFixed(2)} — QUEUE SELF-FEEDING`;
    } else {
      this.banner.classList.remove('show');
    }
  }
}
