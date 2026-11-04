/**
 * CROWD PRESSURE — an analog galvanometer that reads the museum's busiest room.
 * Needle angle is a pure function of max rho (Erlang C utilization) of the
 * rooms in the live simulation. No model, no motion — the instrument is honest.
 * Built in the anatomy idiom: stand, bezel, tick ruler, lit subject (the needle).
 */

const NS = 'http://www.w3.org/2000/svg';

export class CrowdPressureDial {
  private needleEl: SVGGElement | null = null;
  private target = 0;       // 0..1 (max rho)
  private shown = 0;        // eased display value
  private raf: number | null = null;
  readonly el: HTMLDivElement;

  constructor() {
    const wrap = document.createElement('div');
    wrap.className = 'dial-plate';
    wrap.innerHTML = `
      <div class="plate-title"><span>// PRESSURE GAUGE</span><em>CG-04</em></div>
      <svg viewBox="0 0 220 178" role="img" aria-label="Crowd pressure gauge — maximum room utilization">${this.svgBody()}</svg>
      <div class="plate-caption">MAX RHO ACROSS ALL ROOMS &mdash; MODEL: ERLANG C / M/M/c</div>`;
    this.el = wrap;
    this.needleEl = wrap.querySelector('#needle-group');
    this.setRho(0);
  }

  private polar(cx: number, cy: number, r: number, deg: number) {
    const a = ((deg - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
  }

  private svgBody(): string {
    const cx = 110, cy = 82, R = 56;
    const A_MIN = -125, A_MAX = 125;
    const parts: string[] = [];

    // --- bezel: heavy base with corner screws ---
    parts.push(`<rect x="6" y="6" width="208" height="166" rx="4" fill="#15181a" stroke="#22261f" stroke-width="1.5"/>`);
    parts.push(`<rect x="10" y="10" width="200" height="158" rx="2" fill="none" stroke="#0a0c0a" stroke-width="1"/>`);
    const screws = [[20, 19], [200, 19], [20, 159], [200, 159]];
    for (const [sx, sy] of screws) {
      parts.push(`<circle cx="${sx}" cy="${sy}" r="3.1" fill="#20241f" stroke="#050705" stroke-width="0.8"/>`);
      parts.push(`<line x1="${sx - 2}" y1="${sy}" x2="${sx + 2}" y2="${sy}" stroke="#333830" stroke-width="1"/>`);
    }

    // --- mounting feet (brass, bolted) ---
    for (const fx of [44, 158]) {
      parts.push(`<rect x="${fx}" y="150" width="22" height="14" fill="#8a6f3a" stroke="#141005" stroke-width="1"/>`);
      parts.push(`<circle cx="${fx + 11}" cy="157" r="2.4" fill="#141005"/>`);
      parts.push(`<circle cx="${fx + 11}" cy="157" r="1.1" fill="#e4c268"/>`);
    }

    // --- dial face: dark steel, engraved rings ---
    parts.push(`<circle cx="${cx}" cy="${cy}" r="${R}" fill="#0e100e" stroke="#232822" stroke-width="2"/>`);
    parts.push(`<circle cx="${cx}" cy="${cy}" r="${R - 9}" fill="none" stroke="#141712" stroke-width="1"/>`);

    // --- red zone: rho >= 0.85 arc ---
    const arc = (fromRho: number, toRho: number, r: number) => {
      const a0 = A_MIN + fromRho * (A_MAX - A_MIN);
      const a1 = A_MIN + toRho * (A_MAX - A_MIN);
      const p0 = this.polar(cx, cy, r, a0);
      const p1 = this.polar(cx, cy, r, a1);
      return `M ${p0.x.toFixed(2)} ${p0.y.toFixed(2)} A ${r} ${r} 0 0 1 ${p1.x.toFixed(2)} ${p1.y.toFixed(2)}`;
    };
    parts.push(`<path d="${arc(0.85, 1.0, R - 13)}" fill="none" stroke="#E61919" stroke-width="5" stroke-opacity="0.9"/>`);

    // --- tick ruler ---
    for (let i = 0; i <= 10; i++) {
      const rho = i / 10;
      const ang = A_MIN + rho * (A_MAX - A_MIN);
      const major = i === 0 || i === 5 || i === 8 || i === 10;
      const r1 = R - (major ? 17 : 12);
      const r2 = R - 6;
      const p0 = this.polar(cx, cy, r1, ang);
      const p1 = this.polar(cx, cy, r2, ang);
      const hot = rho >= 0.85;
      parts.push(`<line x1="${p0.x.toFixed(2)}" y1="${p0.y.toFixed(2)}" x2="${p1.x.toFixed(2)}" y2="${p1.y.toFixed(2)}" stroke="${hot ? '#ff5a4e' : major ? '#d7d9cb' : '#71766a'}" stroke-width="${major ? 2.2 : 1.2}"/>`);
    }
    // tick labels 0, 0.5, 0.85, 1.0
    const labels: Array<[number, string]> = [[0, '0'], [0.5, '0.5'], [0.8, '.8'], [1.0, '1.0']];
    for (const [rho, txt] of labels) {
      const ang = A_MIN + rho * (A_MAX - A_MIN);
      const p = this.polar(cx, cy, R - 24, ang);
      const hot = rho >= 0.85;
      parts.push(`<text x="${p.x.toFixed(2)}" y="${(p.y + 3).toFixed(2)}" text-anchor="middle" font-family="'IBM Plex Mono', monospace" font-size="8.5" fill="${hot ? '#ff5a4e' : '#b8bba9'}">${txt}</text>`);
    }

    // --- engraved face text ---
    parts.push(`<text x="${cx}" y="${cy + 26}" text-anchor="middle" font-family="'IBM Plex Mono', monospace" font-size="8.2" letter-spacing="2.2" fill="#6d7264">CROWD PRESSURE</text>`);
    parts.push(`<text x="${cx}" y="${cy + 38}" text-anchor="middle" font-family="'IBM Plex Mono', monospace" font-size="6.2" letter-spacing="1.4" fill="#4c5045">LOAD (p)/CAPACITY</text>`);

    // --- needle shadow (offset, then needle, then hub) ---
    const needle = (offsetX: number, offsetY: number, groupId: string) => `
      <g id="${groupId}" transform="translate(${cx + offsetX}, ${cy + offsetY})">
        <polygon points="0,-37 -3.6,5 -1.3,5 -1.3,13 -6.5,13 -6.5,17 6.5,17 6.5,13 1.3,13 1.3,5 3.6,5" fill="#e4c268" stroke="#241c08" stroke-width="1" stroke-linejoin="round"/>
        <polygon points="0,-37 -1.4,5 0,5 1.4,5" fill="#f7e29a"/>
      </g>`;
    parts.push(needle(2.2, 2.2, 'needle-shadow').replace('#e4c268', '#00000055').replace('#f7e29a', '#00000033'));
    parts.push(needle(0, 0, 'needle-group'));
    parts.push(`<circle cx="${cx}" cy="${cy}" r="6.4" fill="#1c1e1c" stroke="#050705" stroke-width="1.2"/>`);
    parts.push(`<circle cx="${cx}" cy="${cy}" r="2.1" fill="#e4c268"/>`);

    // --- glass highlight (thin arc, upper-left) ---
    parts.push(`<path d="${arc(0.02, 0.30, R - 31)}" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-opacity="0.07" stroke-linecap="round" transform="rotate(0 ${cx} ${cy})"/>`);

    return parts.join('\n');
  }

  private angleFor(rho: number): number {
    const clamped = Math.max(0, Math.min(1, rho));
    return -125 + clamped * 250;
  }

  setRho(rho: number) {
    this.target = Math.max(0, Math.min(1, rho));
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      this.shown = this.target;
      this.applyAngle();
      return;
    }
    if (this.raf === null) this.tick();
  }

  private applyAngle() {
    if (!this.needleEl) return;
    this.needleEl.setAttribute('transform', `rotate(${this.angleFor(this.shown)} 110 82)`);
  }

  private tick() {
    const stiffness = 90, damping = 14;
    let vel = 0;
    const step = () => {
      const force = (this.target - this.shown) * stiffness;
      vel = (vel + force * 0.016) * (1 - damping * 0.016);
      this.shown += vel * 0.016;
      this.applyAngle();
      if (Math.abs(this.target - this.shown) > 0.0005 || Math.abs(vel) > 0.0005) {
        this.raf = requestAnimationFrame(step);
      } else {
        this.shown = this.target;
        this.applyAngle();
        this.raf = null;
      }
    };
    this.raf = requestAnimationFrame(step);
  }
}
