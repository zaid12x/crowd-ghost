import * as THREE from 'three';
import { GhostSocket } from './net/ws';

let WORLD_W = 40;
let WORLD_H = 30;

const hud = document.getElementById('hud')!;
const app = document.getElementById('app')!;

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.setClearColor(0x050805);
app.appendChild(renderer.domElement);

const scene = new THREE.Scene();
// ortho frustum is in VIEW space — center it on the look axis
const camera = new THREE.OrthographicCamera(-WORLD_W / 2, WORLD_W / 2, WORLD_H / 2, -WORLD_H / 2, 0.1, 100);
camera.position.set(WORLD_W / 2, WORLD_H / 2, 50);
camera.lookAt(WORLD_W / 2, WORLD_H / 2, 0);

// unit ground, scaled to world bounds (size arrives from /api/health)
const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(1, 1),
  new THREE.MeshBasicMaterial({ color: 0x0a120a })
);
ground.scale.set(WORLD_W, WORLD_H, 1);
ground.position.set(WORLD_W / 2, WORLD_H / 2, -0.5);
scene.add(ground);

// instanced dots for agents
const MAX_AGENTS = 512;
const dotGeo = new THREE.CircleGeometry(0.38, 12);
const dotMat = new THREE.MeshBasicMaterial({ color: 0x39ff14 });
const dots = new THREE.InstancedMesh(dotGeo, dotMat, MAX_AGENTS);
dots.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
dots.frustumCulled = false; // instanced bounds are stale as agents move
dots.count = 0;
scene.add(dots);

const dummy = new THREE.Object3D();

function layoutWorld(w: number, h: number) {
  WORLD_W = w; WORLD_H = h;
  camera.left = -w / 2; camera.right = w / 2; camera.top = h / 2; camera.bottom = -h / 2;
  camera.position.set(w / 2, h / 2, 50);
  camera.lookAt(w / 2, h / 2, 0);
  camera.updateProjectionMatrix();
  ground.scale.set(w, h, 1);
  ground.position.set(w / 2, h / 2, -0.5);
}

let levelName = '';
fetch('/api/health')
  .then((r) => r.json())
  .then((h) => {
    if (h?.bounds) layoutWorld(h.bounds[0], h.bounds[1]);
    levelName = h?.name ?? '';
  })
  .catch(() => {});

const socket = new GhostSocket();
socket.onStatus = (s) => { hud.textContent = `CROWD GHOST\n${s}`; };
socket.onFrame = (f) => {
  dots.count = Math.min(f.nAgents, MAX_AGENTS);
  for (let i = 0; i < dots.count; i++) {
    dummy.position.set(f.agents[i * 4], f.agents[i * 4 + 1], 0);
    dummy.updateMatrix();
    dots.setMatrixAt(i, dummy.matrix);
  }
  dots.instanceMatrix.needsUpdate = true;
  hud.textContent = `CROWD GHOST\n${levelName}\nTICK ${f.tick}\nAGENTS ${f.nAgents}`;
};
socket.connect();
(window as unknown as { __ghost: unknown }).__ghost = { camera, renderer, scene };

addEventListener('resize', () => {
  renderer.setSize(innerWidth, innerHeight);
  camera.left = -WORLD_W / 2; camera.right = WORLD_W / 2;
  camera.top = WORLD_H / 2; camera.bottom = -WORLD_H / 2;
  camera.updateProjectionMatrix();
});

renderer.setAnimationLoop(() => {
  // self-heal: embedded browsers can resize the canvas buffer without firing resize
  const c = renderer.domElement;
  const pr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.floor(c.clientWidth * pr);
  const h = Math.floor(c.clientHeight * pr);
  if (c.width !== w || c.height !== h) {
    renderer.setPixelRatio(pr);
    renderer.setSize(c.clientWidth, c.clientHeight, false);
  }
  renderer.render(scene, camera);
});
