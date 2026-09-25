// EdgeSwarm 3D digital twin (Three.js, served locally: works offline).
// A pure viewer: it draws the snapshot from /api/swarm/state and reports clicks.
// It never changes what the robots do.
import * as THREE from '/static/three/three.module.js';
import { OrbitControls } from '/static/three/examples/jsm/controls/OrbitControls.js';
import { CSS2DRenderer, CSS2DObject } from '/static/three/examples/jsm/renderers/CSS2DRenderer.js';
import { RoundedBoxGeometry } from '/static/three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { RoomEnvironment } from '/static/three/examples/jsm/environments/RoomEnvironment.js';

const COMM_COLOR = { CONNECTED: 0x22c55e, DEGRADED: 0xfab219, PREDICTIVE_LOCAL: 0xf97316, SAFE_FALLBACK: 0xef4444, RECOVERED: 0x3b82f6 };
const THEMES = {
  dark: { bg: 0x0b1220, fog: 0x0b1220, floor: '#1a2233', line: 'rgba(148,163,184,0.16)', aisle: 'rgba(250,204,21,0.55)', hemiSky: 0x9fb4d8, hemiGround: 0x1b2230, hemi: 0.75, sun: 1.6 },
  light: { bg: 0xe8eef6, fog: 0xe8eef6, floor: '#dfe5ec', line: 'rgba(71,85,105,0.18)', aisle: 'rgba(234,179,8,0.85)', hemiSky: 0xffffff, hemiGround: 0x9aa4b1, hemi: 0.95, sun: 1.9 },
};
const ROBOT_EMPTY = 0x2f7de1, ROBOT_LOADED = 0xf2702a;
const STATE_ICON = { IDLE: 'idle', TO_PICKUP: '→ pick', PICKING: 'picking', TO_DROP: '→ drop', DROPPING: 'dropping', TO_CHARGE: '→ charger', CHARGING: '⚡ charging', TO_HOME: '→ home', YIELDING: 'giving way', DEPLETED: 'battery empty' };

function supportsWebGL() {
  try { const c = document.createElement('canvas'); return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl'))); } catch (e) { return false; }
}

class SwarmTwin3D {
  constructor(container, { onCellClick, onHover } = {}) {
    this.el = container;
    this.onCellClick = onCellClick || (() => {});
    this.onHover = onHover || (() => {});
    this.W = 0; this.H = 0; this.mapKey = '';
    this.robots = new Map(); this.humans = []; this.keys = {};
    this.tickMs = 350; this.lastUpdate = performance.now();
    this.follow = null; this.autoRotate = false; this.dark = true;
    this.t0 = performance.now(); this.fading = []; this.sensorsOn = true; this.cellSec = 0.35;

    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.domElement.id = 'twin3dCanvas';
    this.el.appendChild(this.renderer.domElement);

    this.labels = new CSS2DRenderer();
    this.labels.domElement.className = 'twin3d-labels';
    this.el.appendChild(this.labels.domElement);

    this.scene = new THREE.Scene();
    try { const pm = new THREE.PMREMGenerator(this.renderer); this.scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture; this.scene.environmentIntensity = 0.45; } catch (e) {}
    this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI * 0.47;
    this.controls.minDistance = 1.2;
    this.controls.maxDistance = 90;

    this.hemi = new THREE.HemisphereLight(0xffffff, 0x444444, 0.9);
    this.scene.add(this.hemi);
    this.sun = new THREE.DirectionalLight(0xffffff, 1.7);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.bias = -0.0004;
    this.sun.shadow.normalBias = 0.02;
    this.scene.add(this.sun, this.sun.target);

    this.static = new THREE.Group(); this.dynamic = new THREE.Group(); this.overlay = new THREE.Group();
    this.scene.add(this.static, this.dynamic, this.overlay);

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.floorPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    this._bindPointer();

    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(this.el);
    this.setTheme(true);
    this.resize();
    this._loop = this._loop.bind(this);
    requestAnimationFrame(this._loop);
  }

  // ------------------------------------------------------------------ helpers
  w(x, y, h = 0) { return new THREE.Vector3(x - this.W / 2 + 0.5, h, y - this.H / 2 + 0.5); }

  setTheme(dark) {
    this.dark = dark;
    const t = THEMES[dark ? 'dark' : 'light'];
    this.theme = t;
    this.scene.background = new THREE.Color(t.bg);
    this.scene.fog = new THREE.Fog(t.fog, 45, 120);
    this.hemi.color.setHex(t.hemiSky); this.hemi.groundColor.setHex(t.hemiGround); this.hemi.intensity = t.hemi;
    this.sun.intensity = t.sun;
    if (this.floor) this._paintFloor();
    if (this.apron) this.apron.material.color.setHex(dark ? 0x0f1726 : 0xcfd7e1);
    if (this.wallMat) this.wallMat.color.setHex(dark ? 0x3b4456 : 0xaab3bf);
    this.el.classList.toggle('light', !dark);
  }

  resize() {
    const w = this.el.clientWidth || 600, h = this.el.clientHeight || 500;
    this.renderer.setSize(w, h, false);
    this.renderer.domElement.style.width = w + 'px';
    this.renderer.domElement.style.height = h + 'px';
    this.labels.setSize(w, h);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  view(name) {
    const D = Math.max(this.W, this.H);
    this.follow = null;
    if (name === 'top') { this.camera.position.set(0, D * 1.35, 0.01); this.controls.target.set(0, 0, 0); }
    else if (name === 'side') { this.camera.position.set(0, D * 0.35, D * 1.05); this.controls.target.set(0, 0, 0); }
    else { this.camera.position.set(-D * 0.46, D * 0.6, D * 0.64); this.controls.target.set(0, 0, 0); }
    this.controls.update();
  }

  setFollow(id) { this.follow = id; }
  setSensors(on) { this.sensorsOn = on; }
  setAutoRotate(on) { this.autoRotate = on; this.controls.autoRotate = on; this.controls.autoRotateSpeed = 0.6; }

  // ------------------------------------------------------------------ static world
  _clear(group) {
    while (group.children.length) {
      const o = group.children.pop();
      o.traverse(n => { if (n.geometry) n.geometry.dispose(); if (n.material) [].concat(n.material).forEach(m => { if (m.map) m.map.dispose(); m.dispose(); }); if (n.isCSS2DObject) n.element.remove(); });
    }
  }

  _paintFloor() {
    const px = 48, t = this.theme, W = this.W, H = this.H;
    const c = document.createElement('canvas');
    c.width = W * px; c.height = H * px;
    const g = c.getContext('2d');
    g.fillStyle = t.floor; g.fillRect(0, 0, c.width, c.height);
    // subtle concrete speckle
    for (let i = 0; i < W * H * 6; i++) { g.fillStyle = `rgba(${this.dark ? '255,255,255' : '0,0,0'},${Math.random() * 0.035})`; g.fillRect(Math.random() * c.width, Math.random() * c.height, 2, 2); }
    g.strokeStyle = t.line; g.lineWidth = 1;
    for (let x = 0; x <= W; x++) { g.beginPath(); g.moveTo(x * px + .5, 0); g.lineTo(x * px + .5, c.height); g.stroke(); }
    for (let y = 0; y <= H; y++) { g.beginPath(); g.moveTo(0, y * px + .5); g.lineTo(c.width, y * px + .5); g.stroke(); }
    // yellow safety borders around racks
    g.strokeStyle = t.aisle; g.lineWidth = 3;
    const blocked = this.blockedSet;
    for (const k of blocked) {
      const [x, y] = k.split(',').map(Number);
      if (x === 0 || y === 0 || x === W - 1 || y === H - 1) continue;
      if (!blocked.has(`${x - 1},${y}`)) { g.beginPath(); g.moveTo(x * px - 2, y * px); g.lineTo(x * px - 2, (y + 1) * px); g.stroke(); }
      if (!blocked.has(`${x + 1},${y}`)) { g.beginPath(); g.moveTo((x + 1) * px + 2, y * px); g.lineTo((x + 1) * px + 2, (y + 1) * px); g.stroke(); }
      if (!blocked.has(`${x},${y - 1}`)) { g.beginPath(); g.moveTo(x * px, y * px - 2); g.lineTo((x + 1) * px, y * px - 2); g.stroke(); }
      if (!blocked.has(`${x},${y + 1}`)) { g.beginPath(); g.moveTo(x * px, (y + 1) * px + 2); g.lineTo((x + 1) * px, (y + 1) * px + 2); g.stroke(); }
    }
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    if (this.floor.material.map) this.floor.material.map.dispose();
    this.floor.material.map = tex;
    this.floor.material.needsUpdate = true;
  }

  _buildStatic(map) {
    this._clear(this.static);
    this.W = map.width; this.H = map.height;
    this.blockedSet = new Set(map.blocked.map(([x, y]) => `${x},${y}`));
    const W = this.W, H = this.H;

    // floor + an outer apron
    const apron = new THREE.Mesh(new THREE.PlaneGeometry(W + 30, H + 30), new THREE.MeshStandardMaterial({ color: this.dark ? 0x0f1726 : 0xcfd7e1, roughness: 1 }));
    apron.rotation.x = -Math.PI / 2; apron.position.y = -0.02; apron.receiveShadow = true; this.apron = apron;
    this.static.add(apron);
    this.floor = new THREE.Mesh(new THREE.PlaneGeometry(W, H), new THREE.MeshStandardMaterial({ roughness: 0.92, metalness: 0.02 }));
    this.floor.rotation.x = -Math.PI / 2; this.floor.receiveShadow = true;
    this.static.add(this.floor);
    this._paintFloor();

    const walls = [], racks = [];
    map.blocked.forEach(([x, y]) => ((x === 0 || y === 0 || x === W - 1 || y === H - 1) ? walls : racks).push([x, y]));

    // perimeter walls
    const m4 = new THREE.Matrix4();
    this.wallMat = new THREE.MeshStandardMaterial({ color: this.dark ? 0x3b4456 : 0xaab3bf, roughness: 0.85 });
    const wallMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 0.7, 1), this.wallMat, walls.length);
    walls.forEach(([x, y], i) => { const p = this.w(x, y, 0.35); m4.makeTranslation(p.x, p.y, p.z); wallMesh.setMatrixAt(i, m4); });
    wallMesh.castShadow = wallMesh.receiveShadow = true;
    this.static.add(wallMesh);

    // pallet racks: orange uprights, blue beams, cargo boxes on two levels
    const RH = 1.72;
    const post = new THREE.InstancedMesh(new THREE.BoxGeometry(0.07, RH, 0.07), new THREE.MeshStandardMaterial({ color: 0xe8741e, roughness: 0.55, metalness: 0.3 }), racks.length * 4);
    const beam = new THREE.InstancedMesh(new THREE.BoxGeometry(0.92, 0.035, 0.9), new THREE.MeshStandardMaterial({ color: 0x9fb3c8, roughness: 0.45, metalness: 0.55 }), racks.length * 3);
    const box = new THREE.InstancedMesh(new RoundedBoxGeometry(0.36, 0.3, 0.36, 2, 0.03), new THREE.MeshStandardMaterial({ roughness: 0.8 }), racks.length * 6);
    const boxCols = [0xc49a6c, 0xb5895a, 0xd6b183, 0x9c7a54, 0x7aa0c4];
    let pi = 0, bi = 0, ci = 0;
    const rnd = (a) => { const s = Math.sin(a * 12.9898) * 43758.5453; return s - Math.floor(s); };
    racks.forEach(([x, y], k) => {
      const c = this.w(x, y);
      [[-0.43, -0.43], [0.43, -0.43], [-0.43, 0.43], [0.43, 0.43]].forEach(([dx, dz]) => { m4.makeTranslation(c.x + dx, RH / 2, c.z + dz); post.setMatrixAt(pi++, m4); });
      [0.1, 0.72, 1.34].forEach(h => { m4.makeTranslation(c.x, h, c.z); beam.setMatrixAt(bi++, m4); });
      [[0.12, -0.2, -0.2], [0.12, 0.2, 0.18], [0.74, -0.18, 0.2], [0.74, 0.2, -0.16], [1.36, -0.19, 0.02], [1.36, 0.2, -0.1]].forEach(([h, dx, dz], j) => {
        const r = rnd(x * 31 + y * 17 + j);
        if (r < 0.18) { m4.makeScale(0.0001, 0.0001, 0.0001); }
        else { m4.makeRotationY((r - 0.5) * 0.4); m4.setPosition(c.x + dx, h + 0.18, c.z + dz); }
        box.setMatrixAt(ci, m4); box.setColorAt(ci, new THREE.Color(boxCols[Math.floor(r * 97) % boxCols.length])); ci++;
      });
    });
    [post, beam, box].forEach(m => { m.castShadow = true; m.receiveShadow = true; this.static.add(m); });

    // charging docks: glowing pad + post
    this.dockPads = [];
    map.docks.forEach(([x, y]) => {
      const p = this.w(x, y);
      const pad = new THREE.Mesh(new THREE.CircleGeometry(0.42, 40), new THREE.MeshStandardMaterial({ color: 0x16a34a, emissive: 0x22c55e, emissiveIntensity: 0.6, transparent: true, opacity: 0.85 }));
      pad.rotation.x = -Math.PI / 2; pad.position.set(p.x, 0.012, p.z);
      const ring = new THREE.Mesh(new THREE.RingGeometry(0.44, 0.48, 40), new THREE.MeshBasicMaterial({ color: 0x4ade80 }));
      ring.rotation.x = -Math.PI / 2; ring.position.set(p.x, 0.014, p.z);
      const postM = new THREE.Mesh(new RoundedBoxGeometry(0.16, 0.5, 0.16, 2, 0.03), new THREE.MeshStandardMaterial({ color: 0x334155, roughness: 0.4, metalness: 0.5 }));
      postM.position.set(p.x + 0.36, 0.25, p.z - 0.36); postM.castShadow = true;
      const bolt = new THREE.Mesh(new THREE.OctahedronGeometry(0.07), new THREE.MeshStandardMaterial({ color: 0x86efac, emissive: 0x22c55e, emissiveIntensity: 2 }));
      bolt.position.set(p.x + 0.36, 0.56, p.z - 0.36);
      this.static.add(pad, ring, postM, bolt);
      this.dockPads.push({ pad, bolt });
    });

    // light rig sized to the map
    const D = Math.max(W, H);
    this.sun.position.set(-D * 0.45, D * 1.1, D * 0.35);
    const cam = this.sun.shadow.camera;
    cam.left = -D * 0.75; cam.right = D * 0.75; cam.top = D * 0.75; cam.bottom = -D * 0.75; cam.near = 1; cam.far = D * 3;
    cam.updateProjectionMatrix();
    this.scene.fog.near = D * 1.6; this.scene.fog.far = D * 4;
    this.view('iso');
  }

  // ------------------------------------------------------------------ robots (realistic conveyor-top AMR)
  // Differential-drive AMR: 2 drive wheels + 4 casters, bumper, front LiDAR, light strip,
  // motor-driven roller deck that transfers totes sideways to/from rack shelves.
  _makeRobot(r) {
    const g = new THREE.Group();          // world position + yaw
    const body = new THREE.Group();       // pitches when accelerating / braking
    g.add(body);
    const M = (o) => new THREE.MeshStandardMaterial(Object.assign({ roughness: 0.45, metalness: 0.2 }, o));
    const shellMat = M({ color: 0xe9edf2, roughness: 0.32, metalness: 0.1 });
    const accentMat = M({ color: ROBOT_EMPTY, roughness: 0.35 });
    const dark = M({ color: 0x1f2937, roughness: 0.75 });
    const steel = M({ color: 0x9aa5b1, roughness: 0.3, metalness: 0.85 });

    const bumper = new THREE.Mesh(new RoundedBoxGeometry(0.66, 0.09, 0.78, 3, 0.04), dark);
    bumper.position.y = 0.075; bumper.castShadow = true;
    const shell = new THREE.Mesh(new RoundedBoxGeometry(0.62, 0.15, 0.74, 4, 0.06), shellMat);
    shell.position.y = 0.19; shell.castShadow = true; shell.receiveShadow = true;
    const band = new THREE.Mesh(new RoundedBoxGeometry(0.635, 0.035, 0.755, 3, 0.017), accentMat);
    band.position.y = 0.2;
    // light strip (status)
    const stripMat = new THREE.MeshStandardMaterial({ color: 0x111111, emissive: 0x22c55e, emissiveIntensity: 1.8 });
    const strip = new THREE.Mesh(new RoundedBoxGeometry(0.645, 0.014, 0.765, 2, 0.007), stripMat);
    strip.position.y = 0.125;
    body.add(bumper, shell, band, strip);

    // drive wheels (spin with distance) + casters
    const wheels = [];
    [-1, 1].forEach(sx => {
      const w = new THREE.Group();
      const tyre = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.05, 24), M({ color: 0x111827, roughness: 0.9 }));
      tyre.rotation.z = Math.PI / 2;
      const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.04, 0.054, 6), steel);
      hub.rotation.z = Math.PI / 2;
      const spoke = new THREE.Mesh(new THREE.BoxGeometry(0.056, 0.012, 0.11), M({ color: 0xcbd5e1, metalness: 0.6 }));
      w.add(tyre, hub, spoke);
      w.position.set(sx * 0.315, 0.075, 0);
      tyre.castShadow = true;
      g.add(w); wheels.push(w);
    });
    [[-0.22, 0.28], [0.22, 0.28], [-0.22, -0.28], [0.22, -0.28]].forEach(([x, z]) => {
      const c = new THREE.Mesh(new THREE.SphereGeometry(0.03, 12, 8), dark); c.position.set(x, 0.03, z); g.add(c);
    });

    // roller-deck top module
    const deck = new THREE.Group();
    deck.position.y = 0.27;
    const frame = new THREE.Mesh(new RoundedBoxGeometry(0.56, 0.05, 0.66, 2, 0.015), M({ color: 0x475569, roughness: 0.5, metalness: 0.5 }));
    frame.position.y = 0.025; frame.castShadow = true;
    deck.add(frame);
    const rollers = new THREE.Group();
    for (let i = 0; i < 7; i++) {
      const rl = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.028, 0.6, 12), steel);
      rl.position.set(-0.24 + i * 0.08, 0.065, 0);
      rl.rotation.x = Math.PI / 2;             // axis along robot z: totes move along robot x (sideways)
      rollers.add(rl);
    }
    deck.add(rollers);
    [-1, 1].forEach(s => { const rail = new THREE.Mesh(new THREE.BoxGeometry(0.56, 0.05, 0.025), M({ color: 0xf59e0b, roughness: 0.4 })); rail.position.set(0, 0.08, s * 0.33); deck.add(rail); });
    body.add(deck);

    // sensors & lights
    const lidar = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.055, 0.06, 20), M({ color: 0x0f172a, roughness: 0.25, metalness: 0.6 }));
    lidar.position.set(0, 0.105, 0.36);
    const lidarRing = new THREE.Mesh(new THREE.TorusGeometry(0.052, 0.007, 6, 24), new THREE.MeshBasicMaterial({ color: 0x38bdf8 }));
    lidarRing.rotation.x = Math.PI / 2; lidarRing.position.set(0, 0.115, 0.36);
    const headMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xf0f9ff, emissiveIntensity: 2.4 });
    const tailMat = new THREE.MeshStandardMaterial({ color: 0x7f1d1d, emissive: 0xff2020, emissiveIntensity: 1.4 });
    [-0.2, 0.2].forEach(x => {
      const h = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.03, 0.012), headMat); h.position.set(x, 0.2, 0.374); body.add(h);
      const t = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.03, 0.012), tailMat); t.position.set(x, 0.2, -0.374); body.add(t);
    });
    const beaconMat = new THREE.MeshStandardMaterial({ color: 0x0b0b0b, emissive: 0x22c55e, emissiveIntensity: 2.5, transparent: true, opacity: 0.95 });
    const beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.07, 16), beaconMat);
    beacon.position.set(0.24, 0.335, -0.3);
    const estop = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.02, 16), M({ color: 0xdc2626 }));
    estop.position.set(-0.24, 0.275, -0.34);
    body.add(lidar, lidarRing, beacon, estop);

    // tote on the deck (visible while carrying)
    const crate = this._tote(0xd1a05c);
    crate.position.y = 0.27 + 0.09 + 0.14; crate.visible = false;
    body.add(crate);

    // ground decals: radio ring, selection ring, charging glow
    const ringMat = new THREE.MeshBasicMaterial({ color: COMM_COLOR.CONNECTED, transparent: true, opacity: 0.85, depthWrite: false });
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.5, 0.55, 48), ringMat);
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.012;
    const sel = new THREE.Mesh(new THREE.RingGeometry(0.62, 0.68, 48), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.95, depthWrite: false }));
    sel.rotation.x = -Math.PI / 2; sel.position.y = 0.014; sel.visible = false;
    const chargeMat = new THREE.MeshBasicMaterial({ color: 0x22d3ee, transparent: true, opacity: 0.0, depthWrite: false, blending: THREE.AdditiveBlending });
    const chargeGlow = new THREE.Mesh(new THREE.CircleGeometry(0.6, 40), chargeMat);
    chargeGlow.rotation.x = -Math.PI / 2; chargeGlow.position.y = 0.011;
    g.add(ring, sel, chargeGlow);

    // LiDAR sweep + safety field (toggle: sensors)
    const sensors = new THREE.Group();
    const sweep = new THREE.Mesh(new THREE.CircleGeometry(1.9, 24, -0.18, 0.36), new THREE.MeshBasicMaterial({ color: 0x34d399, transparent: true, opacity: 0.16, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    sweep.rotation.x = -Math.PI / 2; sweep.position.set(0, 0.03, 0.36);
    const sweepPivot = new THREE.Group(); sweepPivot.position.set(0, 0, 0.36); sweep.position.set(0, 0.03, 0); sweepPivot.add(sweep);
    const fieldMat = new THREE.MeshBasicMaterial({ color: 0xfacc15, transparent: true, opacity: 0.14, depthWrite: false, side: THREE.DoubleSide });
    const field = new THREE.Mesh(new THREE.PlaneGeometry(0.7, 1), fieldMat);
    field.rotation.x = -Math.PI / 2; field.position.set(0, 0.016, 0.4 + 0.5);
    const fieldEdge = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(0.7, 1)), new THREE.LineBasicMaterial({ color: 0xfacc15, transparent: true, opacity: 0.6 }));
    fieldEdge.rotation.x = -Math.PI / 2; fieldEdge.position.copy(field.position);
    sensors.add(sweepPivot, field, fieldEdge);
    g.add(sensors);

    const tag = document.createElement('div');
    tag.className = 'rtag';
    tag.innerHTML = '<b></b><em></em><span class="bat"><i></i></span>';
    const label = new CSS2DObject(tag);
    label.position.set(0, 0.95, 0);
    label.center.set(0.5, 1);
    g.add(label);

    const p0 = this.w(r.pos[0], r.pos[1]);
    const yaw0 = this._yaw(r.heading) ?? 0;
    g.position.copy(p0); g.rotation.y = yaw0;
    g.userData = {
      id: r.id, body, wheels, rollers, accentMat, stripMat, beaconMat, headMat, tailMat, ringMat, chargeMat, crate, sel, tag,
      sensors, sweepPivot, field, fieldEdge, fieldMat,
      lastCell: r.pos.slice(), prevPath: r.path || [], queue: [], v: 0, yaw: yaw0, pitch: 0, roll: 0, wheelA: 0, rollerA: 0,
      prevState: r.state, prevCarry: !!r.carrying, xfer: null, turning: false,
    };
    g.traverse(o => { o.userData.robotId = r.id; });
    this.dynamic.add(g);
    return g;
  }

  _tote(color, glow = false) {
    const g = new THREE.Group();
    const mat = new THREE.MeshStandardMaterial({ color, roughness: 0.75, emissive: glow ? 0xf59e0b : 0x000000, emissiveIntensity: glow ? 0.35 : 0 });
    const b = new THREE.Mesh(new RoundedBoxGeometry(0.44, 0.28, 0.5, 2, 0.03), mat);
    b.castShadow = true; b.receiveShadow = true;
    const tape = new THREE.Mesh(new THREE.BoxGeometry(0.445, 0.04, 0.505), new THREE.MeshStandardMaterial({ color: 0xe8d5b0, roughness: 0.6 }));
    tape.position.y = 0.06;
    const lab = new THREE.Mesh(new THREE.PlaneGeometry(0.16, 0.1), new THREE.MeshBasicMaterial({ color: 0xffffff }));
    lab.position.set(0.223, -0.03, 0); lab.rotation.y = Math.PI / 2;
    const lab2 = lab.clone(); lab2.position.x = -0.223; lab2.rotation.y = -Math.PI / 2;
    g.add(b, tape, lab, lab2);
    g.userData.mat = mat;
    return g;
  }

  _yaw(h) { return (h && (h[0] || h[1])) ? Math.atan2(h[0], h[1]) : null; }

  // neighbouring rack cell of a floor cell (for tote transfer direction)
  _rackSide(cell) {
    const [x, y] = cell;
    const cand = [[1, 0], [-1, 0], [0, 1], [0, -1]].map(([dx, dy]) => [x + dx, y + dy]).filter(([a, b]) => this.blockedSet && this.blockedSet.has(`${a},${b}`));
    const inner = cand.filter(([a, b]) => a > 0 && b > 0 && a < this.W - 1 && b < this.H - 1);
    return (inner[0] || cand[0]) || null;
  }
  _shelfPoint(cell, rack) {
    // point on the lower shelf of `rack`, at the face toward `cell`
    const c = this.w(cell[0], cell[1]), k = this.w(rack[0], rack[1]);
    return k.clone().lerp(c, 0.22).setY(0.1 + 0.02 + 0.14);
  }

  // ------------------------------------------------------------------ update from snapshot
  update(S, opt = {}) {
    if (!S || !S.map) return;
    const key = `${S.map.width}x${S.map.height}:${S.map.blocked.length}:${S.map.blocked.slice(0, 6).join('|')}:${S.map.docks.join('|')}`;
    if (key !== this.mapKey) {
      this.mapKey = key;
      this.robots.forEach(g => { this.dynamic.remove(g); g.userData.tag.remove(); });
      this.robots.clear();
      this._buildStatic(S.map);
    }
    if (opt.dark !== undefined && opt.dark !== this.dark) this.setTheme(opt.dark);
    this.cellSec = Math.max(0.03, ((S.controller && S.controller.tick_interval) || 0.35));
    this.sel = opt.selRobot || null;
    this.S = S;
    if (opt.sensors !== undefined) this.sensorsOn = opt.sensors;

    const seen = new Set();
    S.robots.forEach(r => {
      seen.add(r.id);
      let g = this.robots.get(r.id);
      if (!g) { g = this._makeRobot(r); this.robots.set(r.id, g); }
      const u = g.userData;
      // ---- motion: queue the cells driven since the last snapshot (reconstructed from the previous plan)
      if (r.pos[0] !== u.lastCell[0] || r.pos[1] !== u.lastCell[1]) {
        const pp = u.prevPath || [];
        const k = pp.findIndex((c, i) => i > 0 && c[0] === r.pos[0] && c[1] === r.pos[1]);
        const man = Math.abs(r.pos[0] - u.lastCell[0]) + Math.abs(r.pos[1] - u.lastCell[1]);
        const cells = (k > 0 && k <= 20) ? pp.slice(1, k + 1) : (man === 1 ? [r.pos] : (man <= 14 ? this._bfs(u.lastCell, r.pos) : null));
        if (cells) {
          let prev = u.lastCell;
          cells.forEach(c => { if (c[0] !== prev[0] || c[1] !== prev[1]) u.queue.push(this.w(c[0], c[1])); prev = c; });
        } else { u.queue = []; g.position.copy(this.w(r.pos[0], r.pos[1])); u.v = 0; }   // teleport (reset / new scenario)
        if (u.queue.length > 14) { const keep = u.queue.slice(-3); g.position.copy(u.queue[u.queue.length - 4]); u.queue = keep; }
        u.lastCell = r.pos.slice();
      }
      u.prevPath = r.path || [];
      // ---- tote transfer animations
      if (r.state === 'PICKING' && u.prevState !== 'PICKING') this._startXfer(g, 'pick', r);
      if (r.state === 'DROPPING' && u.prevState !== 'DROPPING') this._startXfer(g, 'drop', r);
      if (!u.xfer) u.crate.visible = !!r.carrying;
      u.prevState = r.state; u.prevCarry = !!r.carrying;
      // ---- looks
      u.accentMat.color.setHex(r.carrying ? ROBOT_LOADED : ROBOT_EMPTY);
      u.ringMat.color.setHex(COMM_COLOR[r.comm_mode] || COMM_COLOR.CONNECTED);
      u.sel.visible = r.id === this.sel;
      u.waiting = !!r.waiting_for || r.state === 'YIELDING';
      u.stateNow = r.state;
      u.radioBad = !r.radio_up || (r.comm_mode && r.comm_mode !== 'CONNECTED' && r.comm_mode !== 'RECOVERED');
      u.tag.style.display = opt.ids === false ? 'none' : '';
      u.tag.classList.toggle('sel', r.id === this.sel);
      u.tag.querySelector('b').textContent = r.id.replace('AMR-', '');
      u.tag.querySelector('em').textContent = STATE_ICON[r.state] || '';
      const bi = u.tag.querySelector('.bat i');
      bi.style.width = Math.max(0, Math.min(100, r.battery)) + '%';
      bi.style.background = r.state === 'CHARGING' ? '#22d3ee' : r.battery < 25 ? '#ef4444' : r.battery < 45 ? '#fab219' : '#22c55e';
      u.state = r;
    });
    for (const [id, g] of this.robots) if (!seen.has(id)) { this.dynamic.remove(g); g.userData.tag.remove(); this.robots.delete(id); }

    this._humans(S.humans || []);
    this._keyed('blockages', JSON.stringify(S.blockages || []), () => this._blockages(S.blockages || []));
    this._keyed('dz', JSON.stringify(S.dead_zones || []) + (S.global_outage ? 'O' : ''), () => this._deadZones(S.dead_zones || [], S.global_outage));
    const open = (S.tasks || []).filter(t => t.delivered_tick == null && !t.cancelled);
    this._keyed('tasks', JSON.stringify(open.map(t => [t.pickup, t.drop, t.picked_by])), () => this._tasks(open));
    this._overlays(S, opt);
  }

  // shortest free-cell route between two cells (used when the robot re-planned between snapshots)
  _bfs(a, b) {
    const key = (x, y) => x + ',' + y, goal = key(b[0], b[1]);
    const prev = new Map([[key(a[0], a[1]), null]]); const q = [a];
    while (q.length) {
      const c = q.shift(); const kc = key(c[0], c[1]);
      if (kc === goal) { const out = []; let k = kc; while (k && k !== key(a[0], a[1])) { out.push(k.split(',').map(Number)); k = prev.get(k); } return out.reverse(); }
      if (prev.size > 600) break;
      for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const n = [c[0] + dx, c[1] + dy], kn = key(n[0], n[1]);
        if (n[0] < 0 || n[1] < 0 || n[0] >= this.W || n[1] >= this.H || prev.has(kn) || this.blockedSet.has(kn)) continue;
        prev.set(kn, kc); q.push(n);
      }
    }
    return [b];
  }

  _startXfer(g, type, r) {
    const u = g.userData;
    const cell = r.pos;
    const rack = this._rackSide(cell);
    const center = this.w(cell[0], cell[1]);
    const side = rack ? this._shelfPoint(cell, rack) : center.clone().add(new THREE.Vector3(Math.sin(u.yaw) * 0.9, 0.26, Math.cos(u.yaw) * 0.9));
    const top = center.clone().setY(0.27 + 0.09 + 0.14);
    const tote = this._tote(0xd1a05c);
    tote.position.copy(type === 'pick' ? side : top);
    tote.rotation.y = u.yaw;
    this.dynamic.add(tote);
    if (type === 'drop') { tote.visible = false; u.crate.visible = true; }
    if (u.xfer && u.xfer.tote) { if (u.xfer.type === 'pick') u.crate.visible = true; this.dynamic.remove(u.xfer.tote); }
    const stationQ = [...u.queue].reverse().find(q => Math.hypot(q.x - center.x, q.z - center.z) < 1e-3);
    if (stationQ) stationQ.stop = true;
    u.xfer = { type, tote, station: center, from: type === 'pick' ? side : top, to: type === 'pick' ? top : side, t0: performance.now(), created: performance.now(), dur: Math.max(350, this.cellSec * 2 * 1000 * 0.85) };
  }

  _stepXfer(g, now) {
    const u = g.userData, x = u.xfer; if (!x) return;
    // wait until the robot has physically arrived and stopped at the station
    if (!x.started) {
      const there = Math.hypot(g.position.x - x.station.x, g.position.z - x.station.z) < 0.05 && u.v < 0.05;
      if (!there && now - x.created < 4 * x.dur + 1500) { x.t0 = now; return; }
      x.started = true; x.t0 = now;
      const at = g.position.clone().setY(0.27 + 0.09 + 0.14);
      if (x.type === 'pick') x.to = at; else x.from = at;
      if (x.type === 'drop') u.crate.visible = false;
    }
    const a = Math.min(1, (now - x.t0) / x.dur);
    const e = a < 0.5 ? 2 * a * a : 1 - Math.pow(-2 * a + 2, 2) / 2;
    // horizontal slide on the rollers, small lift at the start (pick) or end (drop)
    x.tote.visible = true;
    x.tote.position.lerpVectors(x.from, x.to, e);
    x.tote.position.y += Math.sin(a * Math.PI) * 0.04;
    u.rollerA += 0.35;
    if (a >= 1) {
      if (x.type === 'pick') { this.dynamic.remove(x.tote); u.crate.visible = true; u.xfer = null; }
      else {
        // leave the delivered tote on the shelf briefly, then fade it out
        const tote = x.tote; const t0 = now;
        u.xfer = null;
        this.fading.push({ tote, t0 });
      }
    }
  }

  _keyed(name, key, fn) { if (this.keys[name] !== key) { this.keys[name] = key; fn(); } }

  _group(name) {
    if (this[name]) { this._clear(this[name]); return this[name]; }
    this[name] = new THREE.Group(); this.dynamic.add(this[name]); return this[name];
  }

  _humans(list) {
    while (this.humans.length < list.length) {
      const g = new THREE.Group();
      const M = (c, r = 0.7) => new THREE.MeshStandardMaterial({ color: c, roughness: r });
      const limb = (len, rad, mat) => { const pv = new THREE.Group(); const m = new THREE.Mesh(new THREE.CapsuleGeometry(rad, len, 4, 10), mat); m.position.y = -len / 2 - rad; m.castShadow = true; pv.add(m); return pv; };
      const legL = limb(0.3, 0.055, M(0x1e3a8a, 0.85)), legR = limb(0.3, 0.055, M(0x1e3a8a, 0.85));
      legL.position.set(-0.07, 0.46, 0); legR.position.set(0.07, 0.46, 0);
      const torso = new THREE.Group();
      const vest = new THREE.Mesh(new THREE.CapsuleGeometry(0.13, 0.26, 6, 14), new THREE.MeshStandardMaterial({ color: 0xf97316, emissive: 0x7c2d12, emissiveIntensity: 0.25, roughness: 0.6 }));
      vest.castShadow = true;
      const stripe = new THREE.Mesh(new THREE.CylinderGeometry(0.137, 0.137, 0.03, 20), new THREE.MeshStandardMaterial({ color: 0xe5e7eb, emissive: 0x9ca3af, emissiveIntensity: 0.6, metalness: 0.6, roughness: 0.2 }));
      stripe.position.y = -0.02;
      const head = new THREE.Mesh(new THREE.SphereGeometry(0.1, 16, 16), M(0xd6a27c));
      head.position.y = 0.3; head.castShadow = true;
      const helmet = new THREE.Mesh(new THREE.SphereGeometry(0.112, 16, 10, 0, Math.PI * 2, 0, Math.PI / 2), M(0xfacc15, 0.35));
      helmet.position.y = 0.32;
      const armL = limb(0.24, 0.04, M(0xf97316, 0.6)), armR = limb(0.24, 0.04, M(0xf97316, 0.6));
      armL.position.set(-0.17, 0.16, 0); armR.position.set(0.17, 0.16, 0);
      torso.add(vest, stripe, head, helmet, armL, armR);
      torso.position.y = 0.62;
      const halo = new THREE.Mesh(new THREE.RingGeometry(0.36, 0.42, 32), new THREE.MeshBasicMaterial({ color: 0xa855f7, transparent: true, opacity: 0.7, depthWrite: false }));
      halo.rotation.x = -Math.PI / 2; halo.position.y = 0.013;
      g.add(legL, legR, torso, halo);
      g.userData = { from: null, to: new THREE.Vector3(), legL, legR, armL, armR, torso, phase: 0, init: false };
      this.dynamic.add(g); this.humans.push(g);
    }
    this.humans.forEach((g, i) => {
      if (i >= list.length) { g.visible = false; return; }
      g.visible = true;
      const t = this.w(list[i][0], list[i][1]);
      if (!g.userData.init || g.position.distanceTo(t) > 2.5) { g.position.copy(t); g.userData.init = true; }
      g.userData.to = t;
    });
  }

  _blockages(cells) {
    const grp = this._group('blockGrp');
    cells.forEach(([x, y]) => {
      const p = this.w(x, y);
      const pallet = new THREE.Mesh(new RoundedBoxGeometry(0.8, 0.14, 0.8, 2, 0.02), new THREE.MeshStandardMaterial({ color: 0x8b5a2b, roughness: 0.9 }));
      pallet.position.set(p.x, 0.07, p.z); pallet.castShadow = true;
      const load = new THREE.Mesh(new RoundedBoxGeometry(0.62, 0.5, 0.62, 2, 0.03), new THREE.MeshStandardMaterial({ color: 0x475569, roughness: 0.7 }));
      load.position.set(p.x, 0.4, p.z); load.castShadow = true;
      grp.add(pallet, load);
      [[-0.38, -0.38], [0.38, 0.38], [0.38, -0.38], [-0.38, 0.38]].forEach(([dx, dz]) => {
        const cone = new THREE.Mesh(new THREE.ConeGeometry(0.09, 0.32, 16), new THREE.MeshStandardMaterial({ color: 0xff4d1a, emissive: 0x7f1d1d, emissiveIntensity: 0.4 }));
        cone.position.set(p.x + dx, 0.16, p.z + dz); cone.castShadow = true;
        const band = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.065, 0.05, 16), new THREE.MeshStandardMaterial({ color: 0xffffff }));
        band.position.set(p.x + dx, 0.18, p.z + dz);
        grp.add(cone, band);
      });
      const tag = document.createElement('div'); tag.className = 'ztag block'; tag.textContent = 'BLOCKED';
      const l = new CSS2DObject(tag); l.position.set(p.x, 0.95, p.z); grp.add(l);
    });
  }

  _deadZones(zones, outage) {
    const grp = this._group('dzGrp');
    this.dzMats = [];
    zones.forEach(z => {
      const [x0, y0, x1, y1] = z.map(Number);
      const w = x1 - x0 + 1, h = y1 - y0 + 1;
      const c = this.w((x0 + x1) / 2, (y0 + y1) / 2);
      const mat = new THREE.MeshBasicMaterial({ color: 0xef4444, transparent: true, opacity: 0.12, depthWrite: false, side: THREE.DoubleSide });
      const vol = new THREE.Mesh(new THREE.BoxGeometry(w, 2.2, h), mat);
      vol.position.set(c.x, 1.1, c.z);
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w, 2.2, h)), new THREE.LineBasicMaterial({ color: 0xf87171, transparent: true, opacity: 0.8 }));
      edges.position.copy(vol.position);
      grp.add(vol, edges); this.dzMats.push(mat);
      const tag = document.createElement('div'); tag.className = 'ztag dz'; tag.textContent = 'NO WI-FI';
      const l = new CSS2DObject(tag); l.position.set(c.x, 2.35, c.z); grp.add(l);
    });
    const banner = document.getElementById('twin3dOutage');
    if (banner) banner.style.display = outage ? 'block' : 'none';
  }

  _tasks(open) {
    const grp = this._group('taskGrp');
    this.gems = [];
    open.forEach(t => {
      if (!t.picked_by) {
        // the tote waiting on the rack's lower shelf, plus a bobbing marker over the pick face
        const rack = this._rackSide(t.pickup);
        const p = this.w(t.pickup[0], t.pickup[1]);
        if (rack) {
          const tote = this._tote(0xe0a64f, true);
          tote.position.copy(this._shelfPoint(t.pickup, rack));
          tote.rotation.y = rack[0] !== t.pickup[0] ? 0 : Math.PI / 2;
          grp.add(tote);
        }
        const gem = new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.22, 4), new THREE.MeshStandardMaterial({ color: 0xfbbf24, emissive: 0xf59e0b, emissiveIntensity: 1.1, roughness: 0.3 }));
        gem.rotation.x = Math.PI;
        const base = rack ? 0.62 : 0.5;
        const at = rack ? this._shelfPoint(t.pickup, rack) : p;
        gem.position.set(at.x, base, at.z); gem.userData.base = base; gem.userData.phase = Math.random() * 6;
        grp.add(gem); this.gems.push(gem);
      } else {
        const p = this.w(t.drop[0], t.drop[1]);
        const ring = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.3, 32), new THREE.MeshBasicMaterial({ color: 0x60a5fa, transparent: true, opacity: 0.85, depthWrite: false }));
        ring.rotation.x = -Math.PI / 2; ring.position.set(p.x, 0.018, p.z);
        const dot = new THREE.Mesh(new THREE.CircleGeometry(0.08, 20), new THREE.MeshBasicMaterial({ color: 0x60a5fa }));
        dot.rotation.x = -Math.PI / 2; dot.position.set(p.x, 0.019, p.z);
        grp.add(ring, dot);
      }
    });
  }

  _overlays(S, opt) {
    const grp = this._group('ovGrp');
    const robots = S.robots;
    // reserved cells (fading squares)
    if (opt.res !== false) {
      const cells = [];
      robots.forEach(r => (r.path || []).slice(1, 13).forEach((c, i) => cells.push([c, i, r.carrying])));
      if (cells.length) {
        const m = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.34, 0.34), new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.55, depthWrite: false }), cells.length);
        const m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromEuler(new THREE.Euler(-Math.PI / 2, 0, 0)), s = new THREE.Vector3(1, 1, 1);
        const bg = new THREE.Color(this.theme.bg);
        cells.forEach(([c, i, loaded], k) => {
          const p = this.w(c[0], c[1], 0.022);
          m4.compose(p, q, s); m.setMatrixAt(k, m4);
          m.setColorAt(k, new THREE.Color(loaded ? 0xf2702a : 0x3b82f6).lerp(bg, Math.min(0.85, i * 0.07)));
        });
        grp.add(m);
      }
    }
    // planned paths as glowing tubes
    if (opt.paths !== false) robots.forEach(r => {
      const p = r.path || []; if (p.length < 2) return;
      const pts = []; let last = null;
      p.forEach(c => { const k = c.join(','); if (k !== last) pts.push(this.w(c[0], c[1], 0.05)); last = k; });
      if (pts.length < 2) return;
      const curve = new THREE.CatmullRomCurve3(pts, false, 'catmullrom', 0.1);
      const selR = r.id === this.sel;
      const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, Math.min(200, pts.length * 6), selR ? 0.045 : 0.03, 6, false),
        new THREE.MeshBasicMaterial({ color: selR ? 0xffffff : (r.carrying ? 0xfb923c : 0x60a5fa), transparent: true, opacity: selR ? 0.95 : 0.7 }));
      grp.add(tube);
      if (r.goal) {
        const gp = this.w(r.goal[0], r.goal[1]);
        const flag = new THREE.Mesh(new THREE.ConeGeometry(0.1, 0.24, 4), new THREE.MeshBasicMaterial({ color: selR ? 0xffffff : (r.carrying ? 0xfb923c : 0x60a5fa) }));
        flag.rotation.x = Math.PI; flag.position.set(gp.x, 0.32, gp.z); grp.add(flag);
      }
    });
    // AI conflict risk: arcs between robot pairs
    if (opt.risk !== false) robots.forEach(r => (r.risks || []).forEach(k => {
      if (k.conflict < 0.25) return;
      const o = robots.find(x => x.id === k.peer); if (!o) return;
      const a = this.w(r.pos[0], r.pos[1], 0.4), b = this.w(o.pos[0], o.pos[1], 0.4);
      const mid = a.clone().add(b).multiplyScalar(0.5); mid.y = 0.4 + 0.5 + a.distanceTo(b) * 0.18;
      const col = k.conflict >= 0.75 ? 0xef4444 : k.conflict >= 0.5 ? 0xf97316 : 0xfab219;
      const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
      grp.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 24, 0.02 + 0.035 * k.conflict, 6, false), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.85 })));
      const tag = document.createElement('div'); tag.className = 'ztag risk'; tag.textContent = `${Math.round(k.conflict * 100)}%`;
      tag.style.borderColor = '#' + col.toString(16).padStart(6, '0');
      const l = new CSS2DObject(tag); l.position.copy(mid); grp.add(l);
    }));
    // radio range of the selected robot
    if (opt.range && this.sel) {
      const r = robots.find(x => x.id === this.sel);
      if (r) {
        const p = this.w(r.pos[0], r.pos[1], 0.03);
        const disc = new THREE.Mesh(new THREE.CircleGeometry(8, 64), new THREE.MeshBasicMaterial({ color: 0x3b82f6, transparent: true, opacity: 0.08, depthWrite: false }));
        disc.rotation.x = -Math.PI / 2; disc.position.copy(p);
        const edge = new THREE.Mesh(new THREE.RingGeometry(7.95, 8.05, 96), new THREE.MeshBasicMaterial({ color: 0x60a5fa, transparent: true, opacity: 0.7 }));
        edge.rotation.x = -Math.PI / 2; edge.position.copy(p);
        grp.add(disc, edge);
      }
    }
    // selected cell
    if (opt.selCell) {
      const p = this.w(opt.selCell[0], opt.selCell[1], 0.03);
      const sq = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(0.96, 0.96)), new THREE.LineBasicMaterial({ color: this.dark ? 0xffffff : 0x0f172a }));
      sq.rotation.x = -Math.PI / 2; sq.position.copy(p); grp.add(sq);
    }
  }

  // ------------------------------------------------------------------ interaction
  _cellAt(ev) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set(((ev.clientX - rect.left) / rect.width) * 2 - 1, -((ev.clientY - rect.top) / rect.height) * 2 + 1);
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hits = this.raycaster.intersectObjects([...this.robots.values()], true);
    if (hits.length) {
      const id = hits[0].object.userData.robotId;
      const r = this.S && this.S.robots.find(x => x.id === id);
      if (r) return { cell: r.pos.slice(), robot: id };
    }
    const p = new THREE.Vector3();
    if (!this.raycaster.ray.intersectPlane(this.floorPlane, p)) return null;
    const x = Math.floor(p.x + this.W / 2), y = Math.floor(p.z + this.H / 2);
    if (x < 0 || y < 0 || x >= this.W || y >= this.H) return null;
    return { cell: [x, y], robot: null };
  }

  _bindPointer() {
    const el = this.renderer.domElement;
    let down = null;
    el.addEventListener('pointerdown', e => { down = [e.clientX, e.clientY]; });
    el.addEventListener('pointerup', e => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down[0], e.clientY - down[1]); down = null;
      if (moved > 5) return;
      const hit = this._cellAt(e); if (hit) this.onCellClick(hit.cell[0], hit.cell[1], hit.robot);
    });
    el.addEventListener('pointermove', e => {
      if (e.buttons) return;
      const hit = this._cellAt(e);
      this.onHover(hit, e);
      el.style.cursor = hit && hit.robot ? 'pointer' : 'grab';
    });
    el.addEventListener('pointerleave', () => this.onHover(null));
  }

  // ------------------------------------------------------------------ animation loop
  // Kinematic playback of each robot's driven cells: rotate in place at corners (differential
  // drive), accelerate / cruise / brake on straights, wheels spin with distance travelled.
  _drive(g, dt, t) {
    const u = g.userData;
    const cell = this.cellSec || 0.35;
    const catchup = 1 + 0.7 * Math.max(0, u.queue.length - 1);
    const vmax = (1 / cell) * 1.08 * catchup;
    const acc = vmax / (0.22 * cell);
    const omega = (Math.PI / 2) / (0.28 * cell) * catchup;
    let moved = 0, turning = false, v0 = u.v;
    const atSt = u.xfer && Math.hypot(g.position.x - u.xfer.station.x, g.position.z - u.xfer.station.z) < 0.05;
    let budget = (u.xfer && (u.xfer.started || atSt)) ? 0 : dt;
    while (u.queue.length && budget > 1e-5) {
      const tgt = u.queue[0];
      const dx = tgt.x - g.position.x, dz = tgt.z - g.position.z;
      const dist = Math.hypot(dx, dz);
      if (dist < 1e-3) { g.position.x = tgt.x; g.position.z = tgt.z; u.queue.shift(); if (tgt.stop && u.xfer) { u.v = 0; break; } continue; }
      const want = Math.atan2(dx, dz);
      let err = want - u.yaw; while (err > Math.PI) err -= 2 * Math.PI; while (err < -Math.PI) err += 2 * Math.PI;
      if (Math.abs(err) > 0.01) {
        if (u.v > 0.05) { u.v = Math.max(0, u.v - acc * 2 * budget); budget = 0; break; }
        u.v = 0; turning = true;
        const step = Math.sign(err) * Math.min(Math.abs(err), omega * budget);
        u.yaw += step; budget -= Math.abs(step) / omega;
        continue;
      }
      u.yaw = want;
      // brake before a turn or before the last queued cell
      let stopDist = dist;
      if (u.queue.length > 1 && !(tgt.stop && u.xfer)) {
        const n = u.queue[1];
        const straight = Math.abs(Math.atan2(n.x - tgt.x, n.z - tgt.z) - want) < 0.01;
        if (straight) { let k = 1; stopDist = dist; while (k < u.queue.length) { const a = u.queue[k - 1], b = u.queue[k]; if (a.stop && u.xfer) break; if (Math.abs(Math.atan2(b.x - a.x, b.z - a.z) - want) > 0.01) break; stopDist += a.distanceTo(b); k++; } }
      }
      const vAllowed = Math.sqrt(2 * acc * stopDist) + 0.05;
      u.v = Math.min(u.v + acc * budget, vmax, vAllowed);
      const step = Math.min(dist, u.v * budget);
      g.position.x += (dx / dist) * step; g.position.z += (dz / dist) * step;
      moved += step; budget -= step / Math.max(u.v, 1e-3);
      if (step >= dist - 1e-6) { u.queue.shift(); if (tgt.stop && u.xfer) { u.v = 0; break; } }
    }
    if (!u.queue.length && !turning) u.v = Math.max(0, u.v - acc * 3 * dt);
    g.rotation.y = u.yaw;
    // wheels: forward roll + counter-rotation when turning in place
    u.wheelA += moved / 0.075;
    const turnSpin = turning ? 0.3 : 0;
    u.wheels[0].rotation.x = u.wheelA + turnSpin * t * 12;
    u.wheels[1].rotation.x = u.wheelA - turnSpin * t * 12;
    // body pitch from acceleration (nose dips when braking)
    const a = dt > 0 ? (u.v - v0) / dt : 0;
    u.pitch += ((-a * 0.0022) - u.pitch) * Math.min(1, dt * 10);
    u.pitch = Math.max(-0.05, Math.min(0.05, u.pitch));
    u.body.rotation.x = u.pitch;
    u.turning = turning;
    u.speed = u.v;
  }

  _lights(g, t) {
    const u = g.userData, st = u.stateNow;
    let col = 0x22c55e, blink = 0;
    if (st === 'IDLE' || st === 'TO_HOME') col = 0x93c5fd;
    if (st === 'PICKING' || st === 'DROPPING') { col = 0x22d3ee; blink = 6; }
    if (st === 'CHARGING') { col = 0x22d3ee; }
    if (st === 'TO_CHARGE') col = 0x06b6d4;
    if (u.waiting) { col = 0xf59e0b; blink = 3; }
    if (st === 'DEPLETED') { col = 0xef4444; blink = 2; }
    if (u.turning) { col = 0xf59e0b; blink = 5; }
    const on = blink ? (Math.sin(t * blink * Math.PI) > 0 ? 1 : 0.15) : 1;
    u.stripMat.emissive.setHex(col); u.stripMat.emissiveIntensity = 1.9 * on;
    u.beaconMat.emissive.setHex(u.radioBad ? 0xef4444 : col); u.beaconMat.emissiveIntensity = u.radioBad ? (Math.sin(t * 10) > 0 ? 3 : 0.2) : 2.4 * on;
    u.tailMat.emissiveIntensity = (u.speed || 0) < 0.3 && (u.queue.length || u.waiting) ? 3.2 : 1.2;   // brake lights
    u.chargeMat.opacity = st === 'CHARGING' ? 0.25 + 0.2 * Math.sin(t * 4) : 0;
    // sensors
    u.sensors.visible = this.sensorsOn !== false;
    if (u.sensors.visible) {
      u.sweepPivot.rotation.y = t * 7 + (u.id.charCodeAt(u.id.length - 1) || 0);
      const len = 0.35 + Math.min(1.4, (u.speed || 0) * 0.45 * (this.cellSec || 0.35) * 2.2);
      u.field.scale.y = len; u.field.position.z = 0.4 + len / 2;
      u.fieldEdge.scale.y = len; u.fieldEdge.position.z = u.field.position.z;
      const stop = u.waiting;
      u.fieldMat.color.setHex(stop ? 0xef4444 : 0xfacc15);
      u.fieldEdge.material.color.setHex(stop ? 0xef4444 : 0xfacc15);
      u.fieldMat.opacity = stop ? 0.2 : 0.12;
    }
    u.rollers.children.forEach(rl => { rl.rotation.y = u.rollerA; });
  }

  _loop() {
    requestAnimationFrame(this._loop);
    if (!this.el.offsetParent) { this.prevT = null; return; } // hidden
    const now = performance.now();
    const t = (now - this.t0) / 1000;
    const dt = this.prevT ? Math.min(0.1, (now - this.prevT) / 1000) : 0;
    this.prevT = now;
    for (const g of this.robots.values()) { this._drive(g, dt, t); this._stepXfer(g, now); this._lights(g, t); }
    this.fading = (this.fading || []).filter(f => {
      const a = (now - f.t0) / 1500;
      if (a >= 1) { this.dynamic.remove(f.tote); return false; }
      if (a > 0.5) f.tote.position.y -= dt * 0.05, f.tote.scale.setScalar(Math.max(0.01, 1 - (a - 0.5) * 2));
      return true;
    });
    this.humans.forEach(g => {
      if (!g.visible) return;
      const u = g.userData;
      const d = u.to.clone().sub(g.position); d.y = 0;
      const dist = d.length();
      const vmax = 1 / Math.max(0.2, (this.cellSec || 0.35) * 1.4);
      if (dist > 1e-3) {
        const step = Math.min(dist, vmax * dt);
        g.position.addScaledVector(d.normalize(), step);
        const want = Math.atan2(d.x, d.z);
        let err = want - g.rotation.y; while (err > Math.PI) err -= 2 * Math.PI; while (err < -Math.PI) err += 2 * Math.PI;
        g.rotation.y += err * Math.min(1, dt * 10);
        u.phase += step * 9;
      }
      const swing = dist > 1e-3 ? Math.sin(u.phase) * 0.5 : 0;
      u.legL.rotation.x = swing; u.legR.rotation.x = -swing;
      u.armL.rotation.x = -swing * 0.8; u.armR.rotation.x = swing * 0.8;
      u.torso.position.y = 0.62 + (dist > 1e-3 ? Math.abs(Math.cos(u.phase)) * 0.025 : 0);
    });
    (this.gems || []).forEach(g => { g.position.y = g.userData.base + 0.08 * Math.sin(t * 2.6 + g.userData.phase); g.rotation.y = t; });
    (this.dockPads || []).forEach(d => { d.pad.material.emissiveIntensity = 0.45 + 0.25 * Math.sin(t * 2); d.bolt.rotation.y = t * 2; });
    (this.dzMats || []).forEach(m => { m.opacity = 0.09 + 0.06 * Math.sin(t * 3); });
    for (const g of this.robots.values()) { const s = g.userData.sel; if (s.visible) s.scale.setScalar(1 + 0.06 * Math.sin(t * 5)); }
    if (this.follow) {
      const g = this.robots.get(this.follow);
      if (g) {
        const off = this.camera.position.clone().sub(this.controls.target);
        this.controls.target.lerp(g.position, 0.12);
        this.camera.position.copy(this.controls.target).add(off);
      }
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
    this.labels.render(this.scene, this.camera);
  }
}

window.SwarmTwin3D = SwarmTwin3D;
window.SwarmTwin3D.supported = supportsWebGL();
window.dispatchEvent(new Event('swarm3d-ready'));
