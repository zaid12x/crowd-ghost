import * as THREE from 'three';

/** Low-res density grid accumulated from agent positions each frame. */
export class HeatField {
  readonly resX = 64;
  readonly resY: number;
  private data = new Float32Array(0);
  readonly texture: THREE.DataTexture;
  private worldW: number;
  private worldH: number;
  max = 1;

  constructor(worldW: number, worldH: number) {
    this.worldW = worldW;
    this.worldH = worldH;
    this.resY = Math.max(8, Math.round((worldH / worldW) * this.resX));
    this.data = new Float32Array(this.resX * this.resY);
    this.texture = new THREE.DataTexture(this.data as Float32Array<ArrayBuffer>, this.resX, this.resY, THREE.RedFormat, THREE.FloatType);
    this.texture.magFilter = THREE.LinearFilter;
    this.texture.minFilter = THREE.LinearFilter;
    this.texture.wrapS = THREE.ClampToEdgeWrapping;
    this.texture.wrapT = THREE.ClampToEdgeWrapping;
    this.texture.needsUpdate = true;
  }

  update(agents: Float32Array, n: number) {
    const d = this.data;
    for (let i = 0; i < d.length; i++) d[i] *= 0.86; // decay
    const sx = this.resX / this.worldW;
    const sy = this.resY / this.worldH;
    for (let i = 0; i < n; i++) {
      const cx = Math.floor(agents[i * 4] * sx);
      const cy = Math.floor(agents[i * 4 + 1] * sy);
      if (cx >= 0 && cx < this.resX && cy >= 0 && cy < this.resY) {
        d[cy * this.resX + cx] += 1.0;
      }
    }
    // normalize softly: pressure of 1 agent in a cell ≈ visible
    let max = 0;
    for (let i = 0; i < d.length; i++) if (d[i] > max) max = d[i];
    this.max = max;
    this.texture.needsUpdate = true;
  }

  /** 0..1 pressure at a world position (same field the shader sees). */
  sample(x: number, y: number): number {
    const gx = Math.min(this.resX - 1, Math.max(0, Math.floor((x / this.worldW) * this.resX)));
    const gy = Math.min(this.resY - 1, Math.max(0, Math.floor((y / this.worldH) * this.resY)));
    const v = this.data[gy * this.resX + gx] / Math.max(this.max, 1e-3);
    return Math.min(1, v * 1.15);
  }
}
