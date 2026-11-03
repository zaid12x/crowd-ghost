import * as THREE from 'three';

const MAX_AGENTS = 512;
const TRAIL_LEN = 26;

/** Instanced ghost figures + additive phosphor trail points (single draw call each). */
export class AgentField {
  readonly group = new THREE.Group();
  private mesh: THREE.InstancedMesh;
  private colors: THREE.InstancedBufferAttribute;
  private dummy = new THREE.Object3D();
  private trailPts: THREE.Points;
  private trailPos: Float32Array;
  private trailAlpha: Float32Array;
  private trailLife: Float32Array;
  private trailCursor = 0;
  private maxTrail: number;

  constructor() {
    // low-poly ghost: capsule body, dark material with a hot green rim feel (unlit = glows in the dark)
    const body = new THREE.CapsuleGeometry(0.21, 0.78, 2, 10);
    body.translate(0, 0.72, 0);
    const mat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    this.mesh = new THREE.InstancedMesh(body, mat, MAX_AGENTS);
    this.mesh.frustumCulled = false;
    this.mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    this.colors = new THREE.InstancedBufferAttribute(new Float32Array(MAX_AGENTS * 3), 3);
    this.colors.setUsage(THREE.DynamicDrawUsage);
    this.mesh.instanceColor = this.colors;
    this.mesh.count = 0;
    this.group.add(this.mesh);

    // trail points
    this.maxTrail = MAX_AGENTS * TRAIL_LEN;
    this.trailPos = new Float32Array(this.maxTrail * 3);
    this.trailAlpha = new Float32Array(this.maxTrail);
    this.trailLife = new Float32Array(this.maxTrail);
    const tg = new THREE.BufferGeometry();
    tg.setAttribute('position', new THREE.BufferAttribute(this.trailPos, 3).setUsage(THREE.DynamicDrawUsage));
    tg.setAttribute('aAlpha', new THREE.BufferAttribute(this.trailAlpha, 1).setUsage(THREE.DynamicDrawUsage));
    const tm = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      vertexShader: `
        attribute float aAlpha;
        varying float vA;
        void main() {
          vA = aAlpha;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = clamp(160.0 / -mv.z, 1.5, 14.0);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        varying float vA;
        void main() {
          vec2 uv = gl_PointCoord - 0.5;
          float d = length(uv);
          float fall = smoothstep(0.5, 0.0, d);
          gl_FragColor = vec4(0.16, 1.0, 0.35, fall * vA * 0.55);
        }`,
    });
    this.trailPts = new THREE.Points(tg, tm);
    this.trailPts.frustumCulled = false;
    this.group.add(this.trailPts);
  }

  update(agents: Float32Array, n: number, heatPerAgent: (x: number, y: number) => number) {
    const count = Math.min(n, MAX_AGENTS);
    for (let i = 0; i < count; i++) {
      const x = agents[i * 4];
      const y = agents[i * 4 + 1];
      this.dummy.position.set(x, 0, y);
      this.dummy.rotation.set(0, 0, 0);
      this.dummy.updateMatrix();
      this.mesh.setMatrixAt(i, this.dummy.matrix);
      // tint by local pressure: nobody (cool) -> amber -> red
      const h = Math.min(1, heatPerAgent(x, y));
      const r = Math.min(1, 0.15 + h * 1.5);
      const g = Math.max(0.08, 1.0 - h * 1.35);
      this.colors.setXYZ(i, r, g, 0.18);
      // push a trail point every frame
      const c = this.trailCursor % this.maxTrail;
      this.trailPos[c * 3] = x;
      this.trailPos[c * 3 + 1] = 0.35;
      this.trailPos[c * 3 + 2] = y;
      this.trailLife[c] = 1.0;
      this.trailCursor++;
    }
    this.mesh.count = count;
    this.mesh.instanceMatrix.needsUpdate = true;
    this.colors.needsUpdate = true;

    // age trail points
    const lifeDecay = 1.0 / (TRAIL_LEN * 1.4); // ~1.2 s at 30 fps
    for (let i = 0; i < this.maxTrail; i++) {
      if (this.trailLife[i] > 0) {
        this.trailLife[i] = Math.max(0, this.trailLife[i] - lifeDecay);
        this.trailAlpha[i] = this.trailLife[i] * this.trailLife[i];
      } else {
        this.trailAlpha[i] = 0;
      }
    }
    const posAttr = this.trailPts.geometry.getAttribute('position') as THREE.BufferAttribute;
    const alphaAttr = this.trailPts.geometry.getAttribute('aAlpha') as THREE.BufferAttribute;
    posAttr.needsUpdate = true;
    alphaAttr.needsUpdate = true;
  }
}
