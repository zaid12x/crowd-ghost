import * as THREE from 'three';

export type GhostMode = 'ghost' | 'xray' | 'blueprint';

const GLYPH_RAMP = ' .:-=+*#%@'; // 10 glyphs, dimmest -> brightest

/** Renders the scene into a target, then draws a glyph-cell ASCII pass over the screen. */
export class AsciiPass {
  private rt: THREE.WebGLRenderTarget | null = null;
  private atlas: THREE.CanvasTexture;
  private material: THREE.ShaderMaterial;
  private quadScene = new THREE.Scene();
  private quadCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  constructor() {
    this.atlas = this.makeAtlas();
    const quad = new THREE.Mesh(
      new THREE.PlaneGeometry(2, 2),
      undefined as unknown as THREE.Material
    );
    this.material = new THREE.ShaderMaterial({
      depthTest: false,
      depthWrite: false,
      uniforms: {
        tScene: { value: null },
        tAtlas: { value: this.atlas },
        tHeat: { value: null },
        uRes: { value: new THREE.Vector2(1, 1) },
        uCell: { value: 9.0 },
        uTime: { value: 0 },
        uMode: { value: 0 },
        uHeatMax: { value: 1.0 },
      },
      vertexShader: `
        varying vec2 vUv;
        void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`,
      fragmentShader: `
        uniform sampler2D tScene, tAtlas, tHeat;
        uniform vec2 uRes;
        uniform float uCell, uTime, uMode, uHeatMax;
        varying vec2 vUv;

        void main() {
          vec2 pixel = vUv * uRes;
          vec2 cell = floor(pixel / uCell);
          vec2 cellCenter = (cell + 0.5) * uCell / uRes;
          vec2 cellUv = fract(pixel / uCell);

          vec3 sceneCol = texture2D(tScene, cellCenter).rgb;
          float lum = dot(sceneCol, vec3(0.299, 0.587, 0.114));
          lum = clamp(pow(lum, 0.72) * 1.5, 0.0, 1.0);
          float heat = texture2D(tHeat, cellCenter).r / max(uHeatMax, 1e-3);
          heat = clamp(heat, 0.0, 1.0);

          float glyphLum = uMode < 0.5 ? lum : heat;
          float g = floor(clamp(pow(glyphLum, 0.8) * 9.999, 0.0, 9.0));
          float ax = (g + 0.5) / 10.0;
          vec3 glyph = texture2D(tAtlas, vec2(ax, 1.0 - cellUv.y)).rgb;
          float mask = dot(glyph, vec3(0.333));

          // phosphor green -> amber -> danger red by pressure
          vec3 tint = mix(vec3(0.10, 1.0, 0.27), vec3(1.0, 0.72, 0.08), clamp(heat * 1.35, 0.0, 1.0));
          tint = mix(tint, vec3(1.0, 0.12, 0.08), clamp((heat - 0.68) * 3.2, 0.0, 1.0));

          float energy = uMode < 0.5 ? (0.30 + 0.75 * lum) : (0.35 + 0.85 * heat);
          vec3 col = tint * mask * energy;

          // scanlines, vignette, faint flicker
          float scan = 0.90 + 0.10 * sin(gl_FragCoord.y * 1.9);
          float vig = 1.0 - 0.30 * pow(length(vUv - 0.5) * 1.3, 2.4);
          float flick = 0.93 + 0.07 * sin(uTime * 21.0) * sin(uTime * 7.3 + 1.7);
          col *= scan * vig * flick;

          gl_FragColor = vec4(col, 1.0);
        }`,
    });
    quad.material = this.material;
    this.quadScene.add(quad);
  }

  private makeAtlas(): THREE.CanvasTexture {
    const cell = 72;
    const canvas = document.createElement('canvas');
    canvas.width = cell * GLYPH_RAMP.length;
    canvas.height = cell;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#fff';
    ctx.font = `bold ${Math.floor(cell * 0.82)}px "Courier New", monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (let i = 0; i < GLYPH_RAMP.length; i++) {
      ctx.fillText(GLYPH_RAMP[i], i * cell + cell / 2, cell * 0.54);
    }
    const tex = new THREE.CanvasTexture(canvas);
    tex.magFilter = THREE.NearestFilter;
    tex.minFilter = THREE.LinearFilter;
    tex.wrapS = THREE.ClampToEdgeWrapping;
    tex.wrapT = THREE.ClampToEdgeWrapping;
    return tex;
  }

  setHeat(t: THREE.DataTexture, max: number) {
    this.material.uniforms.tHeat.value = t;
    this.material.uniforms.uHeatMax.value = Math.max(max, 1.0) as number;
  }

  resize(width: number, height: number) {
    if (this.rt) this.rt.dispose();
    this.rt = new THREE.WebGLRenderTarget(width, height, {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      depthBuffer: true,
      stencilBuffer: false,
    });
    this.material.uniforms.uRes.value.set(width, height);
  }

  render(
    renderer: THREE.WebGLRenderer,
    scene: THREE.Scene,
    camera: THREE.Camera,
    mode: GhostMode,
    timeMs: number
  ) {
    if (!this.rt) {
      const size = renderer.getDrawingBufferSize(new THREE.Vector2());
      this.resize(size.x, size.y);
    }
    const rt = this.rt!;
    this.material.uniforms.uTime.value = timeMs * 0.001;
    this.material.uniforms.uMode.value = mode === 'xray' ? 1 : 0;

    renderer.setRenderTarget(rt);
    renderer.setClearColor(0x050805, 1);
    renderer.clear();
    renderer.render(scene, camera);

    this.material.uniforms.tScene.value = rt.texture;
    renderer.setRenderTarget(null);
    renderer.render(this.quadScene, this.quadCam);
  }
}
