import * as THREE from 'three';

export interface GeometryPayload {
  id: string;
  bounds: [number, number];
  walls: number[][]; // [x0,y0,x1,y1]
  room_walls: number[][][];  // room polygons for blueprint strokes
  rooms: { id: number; name: string; polygon: number[][]; capacity: number }[];
  doors: { id: string; rooms: (number | null)[]; x: number; y: number; angle: number; width: number }[];
}

const WALL_HEIGHT = 3.1;
const WALL_DEPTH = 0.42;

/** Builds the haunted museum: floor slabs, extruded walls, door gaps already cut, eerie glow. */
export function buildMuseum(geo: GeometryPayload, scene: THREE.Scene) {
  const [W, H] = geo.bounds;
  const group = new THREE.Group();
  group.name = 'museum';

  // abyssal void beyond the walls (the museum floats in darkness)
  const void_ = new THREE.Mesh(
    new THREE.PlaneGeometry(W * 3.2, H * 3.2),
    new THREE.MeshBasicMaterial({ color: 0x020302 })
  );
  void_.rotation.x = -Math.PI / 2;
  void_.position.set(W / 2, -0.02, H / 2);
  group.add(void_);

  // floor slabs with slight tonal variation per room
  const floors = new THREE.Group();
  floors.name = 'floors';
  const floorMats = [0x10160f, 0x121a11, 0x0e140e, 0x141a10];
  geo.rooms.forEach((room, i) => {
    const shape = new THREE.Shape();
    const p = room.polygon;
    // negate y so rotX(-90°) lands (x, z=+y) in the ground plane
    shape.moveTo(p[0][0], -p[0][1]);
    for (let k = 1; k < p.length; k++) shape.lineTo(p[k][0], -p[k][1]);
    shape.closePath();
    const g = new THREE.ShapeGeometry(shape);
    const mat = new THREE.MeshLambertMaterial({ color: floorMats[i % floorMats.length], emissive: 0x141c13 });
    const mesh = new THREE.Mesh(g, mat);
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.y = 0.0;
    floors.add(mesh);
  });
  group.add(floors);

  // walls: dark stone with a faint phosphor edge
  const wallMat = new THREE.MeshLambertMaterial({ color: 0x2c3a2c, emissive: 0x161f16 });
  const edgeMat = new THREE.LineBasicMaterial({ color: 0x2aff5e, transparent: true, opacity: 0.5 });
  const wallSolids = new THREE.Group();
  for (const [x0, y0, x1, y1] of geo.walls) {
    const dx = x1 - x0;
    const dy = y1 - y0;
    const len = Math.hypot(dx, dy);
    if (len < 1e-6) continue;
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    const box = new THREE.Mesh(new THREE.BoxGeometry(len, WALL_HEIGHT, WALL_DEPTH), wallMat);
    box.position.set(cx, WALL_HEIGHT / 2, cy);
    box.rotation.y = Math.atan2(dy, dx) * -1; // align box x to segment (z is flipped)
    wallSolids.add(box);
    // phosphor edge along the wall top
    const edge = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(x0, WALL_HEIGHT + 0.02, y0),
      new THREE.Vector3(x1, WALL_HEIGHT + 0.02, y1),
    ]);
    group.add(new THREE.Line(edge, edgeMat));
  }
  group.add(wallSolids);

  // door lintels: a dim amber bar above each opening
  const lintelMat = new THREE.MeshLambertMaterial({ color: 0x2a2110, emissive: 0x241505 });
  for (const d of geo.doors) {
    const horiz = Math.abs(d.angle) < 1e-6;
    const lintel = new THREE.Mesh(
      new THREE.BoxGeometry(horiz ? d.width : WALL_DEPTH, 0.28, horiz ? WALL_DEPTH : d.width),
      lintelMat
    );
    lintel.position.set(d.x, WALL_HEIGHT - 0.35, d.y);
    group.add(lintel);
  }

  // blueprint strokes (toggled for Blueprint mode)
  const strokes = new THREE.Group();
  strokes.name = 'blueprint';
  const strokeMat = new THREE.LineBasicMaterial({ color: 0x2aff5e, transparent: true, opacity: 0.85 });
  for (const poly of geo.room_walls) {
    const pts = poly.map((p) => new THREE.Vector3(p[0], 0.05, p[1]));
    pts.push(pts[0].clone());
    strokes.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), strokeMat));
  }
  for (const [x0, y0, x1, y1] of geo.walls) {
    strokes.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(x0, 0.05, y0),
        new THREE.Vector3(x1, 0.05, y1),
      ]),
      strokeMat
    ));
  }
  strokes.visible = false;
  group.add(strokes);

  // lighting: cold ambient + one ghostly green wash from above + amber hot-spot near center
  scene.add(new THREE.AmbientLight(0x46523f, 2.3));
  const hemi = new THREE.HemisphereLight(0x46584a, 0x080a08, 1.5);
  scene.add(hemi);
  const dir = new THREE.DirectionalLight(0xa8c0a6, 1.75);
  dir.position.set(W * 0.35, 42, H * 0.25);
  scene.add(dir);
  const greenGlow = new THREE.PointLight(0x2aff5e, 12, W * 1.15, 1.6);
  greenGlow.position.set(W / 2, 7, H / 2);
  scene.add(greenGlow);
  const amber = new THREE.PointLight(0xffa030, 7, W * 0.55, 1.8);
  amber.position.set(W * 0.62, 5.2, H / 2);
  scene.add(amber);

  scene.add(group);
  return { group, wallSolids, strokes, floors, bounds: geo.bounds };
}
