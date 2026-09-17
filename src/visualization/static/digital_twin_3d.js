import * as THREE from '/static/three/three.module.js';
import { OrbitControls } from '/static/three/examples/jsm/controls/OrbitControls.js';

class DigitalTwin3D {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    if (!this.container) return;

    this.scene = null;
    this.camera = null;
    this.renderer = null;
    this.controls = null;
    this.animId = null;

    this.gridWidth = 18;
    this.gridHeight = 18;
    this.cellSize = 2.0; // World units per warehouse cell

    this.robotMeshes = new Map();
    this.shelfMeshes = new Map();
    this.dockMeshes = new Map();
    this.obstacleMeshes = new Map();
    this.pathLines = new Map();
    this.negotiationBeams = [];
    this.deadlockCycleLines = [];

    this.followTargetId = null;
    this.targetCameraPos = null;
    this.targetLookAt = null;

    this.active = false;
    this.initialized = false;
  }

  init() {
    if (this.initialized || !this.container) return;

    const width = this.container.clientWidth || 800;
    const height = this.container.clientHeight || 600;

    // 1. Scene
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x050d11);
    this.scene.fog = new THREE.FogExp2(0x050d11, 0.015);

    // 2. Camera
    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 500);
    this.setIsometricCamera();

    // 3. Renderer
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.container.appendChild(this.renderer.domElement);

    // 4. OrbitControls
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.05; // Do not go below floor
    this.controls.minDistance = 5;
    this.controls.maxDistance = 120;
    this.controls.target.set(
      (this.gridWidth * this.cellSize) / 2,
      0,
      (this.gridHeight * this.cellSize) / 2
    );

    // 5. Lighting
    this.setupLighting();

    // 6. Floor & Static Grid Structure
    this.createWarehouseEnvironment();

    // 7. Event listeners
    window.addEventListener('resize', () => this.onResize());

    this.initialized = true;
    this.animate();
  }

  setupLighting() {
    const ambientLight = new THREE.AmbientLight(0xdff4f7, 0.55);
    this.scene.add(ambientLight);

    const mainSun = new THREE.DirectionalLight(0xffffff, 0.85);
    mainSun.position.set(30, 45, 20);
    mainSun.castShadow = true;
    mainSun.shadow.mapSize.width = 2048;
    mainSun.shadow.mapSize.height = 2048;
    mainSun.shadow.camera.near = 10;
    mainSun.shadow.camera.far = 100;
    const d = 30;
    mainSun.shadow.camera.left = -d;
    mainSun.shadow.camera.right = d;
    mainSun.shadow.camera.top = d;
    mainSun.shadow.camera.bottom = -d;
    this.scene.add(mainSun);

    // Secondary cyan/blue atmospheric fill light
    const fillLight = new THREE.DirectionalLight(0x56d6cf, 0.35);
    fillLight.position.set(-20, 25, -20);
    this.scene.add(fillLight);
  }

  createWarehouseEnvironment() {
    const totalW = this.gridWidth * this.cellSize;
    const totalH = this.gridHeight * this.cellSize;

    // Floor geometry
    const floorGeo = new THREE.PlaneGeometry(totalW, totalH);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0x07151c,
      roughness: 0.8,
      metalness: 0.2,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(totalW / 2, 0, totalH / 2);
    floor.receiveShadow = true;
    this.scene.add(floor);

    // Grid Overlay
    const gridHelper = new THREE.GridHelper(totalW, this.gridWidth, 0x203740, 0x142a31);
    gridHelper.position.set(totalW / 2, 0.02, totalH / 2);
    this.scene.add(gridHelper);

    // Outer Perimeter Guardrails / Low Walls
    const wallMat = new THREE.MeshStandardMaterial({ color: 0x1b3540, metalness: 0.6, roughness: 0.4 });
    const wallThick = 0.3;
    const wallHeight = 0.8;

    const wallNorth = new THREE.Mesh(new THREE.BoxGeometry(totalW, wallHeight, wallThick), wallMat);
    wallNorth.position.set(totalW / 2, wallHeight / 2, 0);
    this.scene.add(wallNorth);

    const wallSouth = new THREE.Mesh(new THREE.BoxGeometry(totalW, wallHeight, wallThick), wallMat);
    wallSouth.position.set(totalW / 2, wallHeight / 2, totalH);
    this.scene.add(wallSouth);

    const wallWest = new THREE.Mesh(new THREE.BoxGeometry(wallThick, wallHeight, totalH), wallMat);
    wallWest.position.set(0, wallHeight / 2, totalH / 2);
    this.scene.add(wallWest);

    const wallEast = new THREE.Mesh(new THREE.BoxGeometry(wallThick, wallHeight, totalH), wallMat);
    wallEast.position.set(totalW, wallHeight / 2, totalH / 2);
    this.scene.add(wallEast);
  }

  // Converts 2D grid coordinates (x, y) into 3D world coordinates (x, 0, z)
  cellToWorld(x, y) {
    return new THREE.Vector3((x + 0.5) * this.cellSize, 0, (y + 0.5) * this.cellSize);
  }

  update(data) {
    if (!this.initialized) {
      this.init();
    }
    if (!data) return;

    this.updateStaticInfrastructure(data);
    this.updateRobots(data.robots || []);
    this.updateDynamicObstacles(data.dynamic_blockages || []);
    this.updateNegotiationBeams(data.robots || []);
    this.updateDeadlockVisuals(data.wfg_cycles || []);

    // Handle smooth follow-camera
    if (this.followTargetId) {
      const mesh = this.robotMeshes.get(this.followTargetId);
      if (mesh) {
        const targetPos = mesh.position.clone();
        this.controls.target.lerp(targetPos, 0.08);
      }
    }
  }

  updateStaticInfrastructure(data) {
    // 1. Static Shelves / Racks
    const obstacles = (data.warehouse && data.warehouse.obstacles) || data.obstacles || [];
    obstacles.forEach(([x, y]) => {
      // Don't render perimeter walls as interior racks
      if (x === 0 || x === this.gridWidth - 1 || y === 0 || y === this.gridHeight - 1) return;
      const key = `${x},${y}`;
      if (!this.shelfMeshes.has(key)) {
        const shelf = this.createShelfRackMesh(x, y);
        this.shelfMeshes.set(key, shelf);
        this.scene.add(shelf);
      }
    });

    // 2. Charging Stations
    const stations = (data.warehouse && data.warehouse.charging_stations) || data.charging_stations || [];
    stations.forEach(([x, y]) => {
      const key = `${x},${y}`;
      if (!this.dockMeshes.has(key)) {
        const dock = this.createChargingDockMesh(x, y);
        this.dockMeshes.set(key, dock);
        this.scene.add(dock);
      }
    });
  }

  createShelfRackMesh(x, y) {
    const group = new THREE.Group();
    const pos = this.cellToWorld(x, y);
    group.position.copy(pos);

    const rackMat = new THREE.MeshStandardMaterial({ color: 0x223842, metalness: 0.5, roughness: 0.5 });
    const binMat1 = new THREE.MeshStandardMaterial({ color: 0x4a7c8f, metalness: 0.2, roughness: 0.7 });
    const binMat2 = new THREE.MeshStandardMaterial({ color: 0x739ba8, metalness: 0.2, roughness: 0.7 });

    // Upright posts
    const postGeo = new THREE.BoxGeometry(0.08, 1.8, 0.08);
    const postOffsets = [[-0.7, -0.7], [0.7, -0.7], [-0.7, 0.7], [0.7, 0.7]];
    postOffsets.forEach(([px, pz]) => {
      const p = new THREE.Mesh(postGeo, rackMat);
      p.position.set(px, 0.9, pz);
      p.castShadow = true;
      group.add(p);
    });

    // Shelves tiers
    const shelfGeo = new THREE.BoxGeometry(1.5, 0.05, 1.5);
    [0.4, 0.9, 1.4, 1.8].forEach(sy => {
      const s = new THREE.Mesh(shelfGeo, rackMat);
      s.position.set(0, sy, 0);
      s.receiveShadow = true;
      group.add(s);
    });

    // Storage Bins on tiers
    const binGeo = new THREE.BoxGeometry(0.55, 0.35, 0.55);
    const bin1 = new THREE.Mesh(binGeo, binMat1);
    bin1.position.set(-0.35, 0.6, -0.35);
    bin1.castShadow = true;
    group.add(bin1);

    const bin2 = new THREE.Mesh(binGeo, binMat2);
    bin2.position.set(0.35, 0.6, 0.35);
    bin2.castShadow = true;
    group.add(bin2);

    const bin3 = new THREE.Mesh(binGeo, binMat1);
    bin3.position.set(0.35, 1.1, -0.35);
    bin3.castShadow = true;
    group.add(bin3);

    return group;
  }

  createChargingDockMesh(x, y) {
    const group = new THREE.Group();
    const pos = this.cellToWorld(x, y);
    group.position.copy(pos);

    // Glowing charging floor pad
    const padGeo = new THREE.BoxGeometry(1.6, 0.06, 1.6);
    const padMat = new THREE.MeshStandardMaterial({
      color: 0x113a30,
      emissive: 0x22c55e,
      emissiveIntensity: 0.45,
      metalness: 0.3,
      roughness: 0.4,
    });
    const pad = new THREE.Mesh(padGeo, padMat);
    pad.position.y = 0.03;
    group.add(pad);

    // Vertical charging tower stanchion
    const towerGeo = new THREE.BoxGeometry(0.3, 1.4, 0.3);
    const towerMat = new THREE.MeshStandardMaterial({ color: 0x1b3540, metalness: 0.7, roughness: 0.3 });
    const tower = new THREE.Mesh(towerGeo, towerMat);
    tower.position.set(0, 0.7, -0.65);
    tower.castShadow = true;
    group.add(tower);

    // Charging icon / indicator light
    const lightGeo = new THREE.SphereGeometry(0.12, 16, 16);
    const lightMat = new THREE.MeshBasicMaterial({ color: 0x7be28b });
    const indicator = new THREE.Mesh(lightGeo, lightMat);
    indicator.position.set(0, 1.35, -0.65);
    group.add(indicator);

    return group;
  }

  createAMRMesh(robot) {
    const group = new THREE.Group();

    // 1. Chassis: Rounded industrial mobile robot body
    const bodyGeo = new THREE.CylinderGeometry(0.65, 0.68, 0.32, 24);
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0x182c35,
      metalness: 0.4,
      roughness: 0.5,
    });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    body.position.y = 0.22;
    body.castShadow = true;
    body.receiveShadow = true;
    group.add(body);

    // 2. Drive Wheels
    const wheelGeo = new THREE.CylinderGeometry(0.18, 0.18, 0.09, 16);
    const wheelMat = new THREE.MeshStandardMaterial({ color: 0x0b1317, roughness: 0.9 });
    const leftWheel = new THREE.Mesh(wheelGeo, wheelMat);
    leftWheel.rotation.z = Math.PI / 2;
    leftWheel.position.set(-0.64, 0.18, 0);
    group.add(leftWheel);

    const rightWheel = new THREE.Mesh(wheelGeo, wheelMat);
    rightWheel.rotation.z = Math.PI / 2;
    rightWheel.position.set(0.64, 0.18, 0);
    group.add(rightWheel);

    // 3. Top LiDAR Dome
    const lidarGeo = new THREE.CylinderGeometry(0.15, 0.15, 0.12, 16);
    const lidarMat = new THREE.MeshStandardMaterial({ color: 0x050d11, metalness: 0.8, roughness: 0.2 });
    const lidar = new THREE.Mesh(lidarGeo, lidarMat);
    lidar.position.set(0, 0.44, 0);
    group.add(lidar);

    // 4. Status Halo LED Ring
    const ringGeo = new THREE.TorusGeometry(0.64, 0.035, 8, 32);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x56d6cf });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.24;
    group.add(ring);
    group.userData.statusRing = ring;

    // 5. Cargo Box Container (toggleable when carrying cargo)
    const cargoGeo = new THREE.BoxGeometry(0.65, 0.48, 0.65);
    const cargoMat = new THREE.MeshStandardMaterial({
      color: 0xf0b35b,
      roughness: 0.8,
      metalness: 0.1,
    });
    const cargo = new THREE.Mesh(cargoGeo, cargoMat);
    cargo.position.set(0, 0.65, 0);
    cargo.castShadow = true;
    cargo.visible = false;
    group.add(cargo);
    group.userData.cargoMesh = cargo;

    // 6. Floating Canvas Billboard Label
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 80;
    const texture = new THREE.CanvasTexture(canvas);
    const spriteMat = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(spriteMat);
    sprite.scale.set(1.6, 0.5, 1.0);
    sprite.position.set(0, 1.45, 0);
    group.add(sprite);
    group.userData.labelSprite = sprite;
    group.userData.labelCanvas = canvas;
    group.userData.labelTexture = texture;

    return group;
  }

  updateRobots(robots) {
    const activeIds = new Set(robots.map(r => r.robot_id));

    // Remove deleted robots
    for (const [id, mesh] of this.robotMeshes.entries()) {
      if (!activeIds.has(id)) {
        this.scene.remove(mesh);
        this.robotMeshes.delete(id);
        const pathLine = this.pathLines.get(id);
        if (pathLine) {
          this.scene.remove(pathLine);
          this.pathLines.delete(id);
        }
      }
    }

    robots.forEach(r => {
      let mesh = this.robotMeshes.get(r.robot_id);
      if (!mesh) {
        mesh = this.createAMRMesh(r);
        this.robotMeshes.set(r.robot_id, mesh);
        this.scene.add(mesh);
      }

      // Smoothly interpolate position towards target
      const targetPos = this.cellToWorld(r.position[0], r.position[1]);
      mesh.position.lerp(targetPos, 0.25);

      // Orientation
      if (r.path && r.path.length > 1) {
        const nextCell = r.path[1];
        const nextPos = this.cellToWorld(nextCell[0], nextCell[1]);
        const dir = nextPos.clone().sub(mesh.position);
        if (dir.lengthSq() > 0.001) {
          const targetAngle = Math.atan2(dir.x, dir.z);
          mesh.rotation.y = THREE.MathUtils.lerp(mesh.rotation.y, targetAngle, 0.2);
        }
      }

      // Status Ring Color
      const ring = mesh.userData.statusRing;
      if (ring) {
        let colorHex = 0x56d6cf; // Idle cyan
        if (r.failed || r.state === 'FAILED') colorHex = 0xef4444; // Red
        else if (r.state.startsWith('DOCK') || r.state === 'CHARGING') colorHex = 0x22c55e; // Green
        else if (r.state === 'WAITING' || r.state === 'NEGOTIATING') colorHex = 0xf59e0b; // Amber
        else if (r.carrying_package_id) colorHex = 0x38bdf8; // Blue
        else if (r.state.startsWith('MOVING')) colorHex = 0x10b981; // Teal-green
        ring.material.color.setHex(colorHex);
      }

      // Cargo Box visibility
      const cargo = mesh.userData.cargoMesh;
      if (cargo) {
        cargo.visible = Boolean(r.carrying_package_id);
      }

      // Update Floating Label
      this.updateRobotLabel(mesh, r);

      // Update Path Spline
      this.updateRobotPathLine(r);
    });

    // Populate Follow AMR dropdown if needed
    const select = document.getElementById('followAmrSelect');
    if (select && select.options.length <= 1 && robots.length > 0) {
      robots.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.robot_id;
        opt.textContent = `Follow ${r.robot_id}`;
        select.appendChild(opt);
      });
    }
  }

  updateRobotLabel(mesh, r) {
    const canvas = mesh.userData.labelCanvas;
    const texture = mesh.userData.labelTexture;
    if (!canvas || !texture) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Dark pill container
    ctx.fillStyle = 'rgba(7, 16, 21, 0.88)';
    ctx.strokeStyle = r.failed ? '#ef4444' : '#56d6cf';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.roundRect(6, 6, canvas.width - 12, canvas.height - 12, 14);
    ctx.fill();
    ctx.stroke();

    // Robot ID & State
    ctx.font = 'bold 26px Inter, sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.fillText(`${r.robot_id}`, 18, 38);

    // Battery / Task Text
    ctx.font = '20px Inter, sans-serif';
    ctx.fillStyle = r.battery < 25 ? '#ef4444' : '#7be28b';
    ctx.fillText(`⚡${Math.round(r.battery)}%  [${r.state}]`, 18, 64);

    texture.needsUpdate = true;
  }

  updateRobotPathLine(r) {
    let line = this.pathLines.get(r.robot_id);
    if (!r.path || r.path.length <= 1) {
      if (line) line.visible = false;
      return;
    }

    const points = r.path.map(([px, py]) => {
      const v = this.cellToWorld(px, py);
      v.y = 0.08;
      return v;
    });

    const geometry = new THREE.BufferGeometry().setFromPoints(points);

    if (!line) {
      const material = new THREE.LineBasicMaterial({
        color: r.carrying_package_id ? 0xf0b35b : 0x56d6cf,
        linewidth: 3,
        transparent: true,
        opacity: 0.75,
      });
      line = new THREE.Line(geometry, material);
      this.scene.add(line);
      this.pathLines.set(r.robot_id, line);
    } else {
      line.geometry.dispose();
      line.geometry = geometry;
      line.material.color.setHex(r.carrying_package_id ? 0xf0b35b : 0x56d6cf);
      line.visible = true;
    }
  }

  updateDynamicObstacles(blockages) {
    const activeKeys = new Set(blockages.map(([x, y]) => `${x},${y}`));

    for (const [key, mesh] of this.obstacleMeshes.entries()) {
      if (!activeKeys.has(key)) {
        this.scene.remove(mesh);
        this.obstacleMeshes.delete(key);
      }
    }

    blockages.forEach(([x, y]) => {
      const key = `${x},${y}`;
      if (!this.obstacleMeshes.has(key)) {
        const obsGeo = new THREE.BoxGeometry(1.6, 1.1, 1.6);
        const obsMat = new THREE.MeshStandardMaterial({
          color: 0xef4444,
          emissive: 0x7f1d1d,
          emissiveIntensity: 0.35,
          roughness: 0.4,
        });
        const obs = new THREE.Mesh(obsGeo, obsMat);
        const pos = this.cellToWorld(x, y);
        obs.position.set(pos.x, 0.55, pos.z);
        obs.castShadow = true;
        this.scene.add(obs);
        this.obstacleMeshes.set(key, obs);
      }
    });
  }

  updateNegotiationBeams(robots) {
    // Clear old beams
    this.negotiationBeams.forEach(b => this.scene.remove(b));
    this.negotiationBeams = [];

    const negotiatingRobots = robots.filter(r => r.state === 'NEGOTIATING');
    if (negotiatingRobots.length >= 2) {
      for (let i = 0; i < negotiatingRobots.length - 1; i++) {
        const r1 = negotiatingRobots[i];
        const r2 = negotiatingRobots[i + 1];
        const p1 = this.cellToWorld(r1.position[0], r1.position[1]);
        const p2 = this.cellToWorld(r2.position[0], r2.position[1]);
        p1.y = 0.4;
        p2.y = 0.4;

        const lineGeo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
        const lineMat = new THREE.LineBasicMaterial({ color: 0xf59e0b, linewidth: 4 });
        const beam = new THREE.Line(lineGeo, lineMat);
        this.scene.add(beam);
        this.negotiationBeams.push(beam);
      }
    }
  }

  updateDeadlockVisuals(cycles) {
    this.deadlockCycleLines.forEach(l => this.scene.remove(l));
    this.deadlockCycleLines = [];

    if (cycles && cycles.length > 0) {
      cycles.forEach(cycle => {
        const points = [];
        cycle.forEach(rid => {
          const mesh = this.robotMeshes.get(rid);
          if (mesh) {
            const pt = mesh.position.clone();
            pt.y = 0.5;
            points.push(pt);
          }
        });
        if (points.length >= 2) {
          points.push(points[0].clone()); // Close loop
          const geo = new THREE.BufferGeometry().setFromPoints(points);
          const mat = new THREE.LineDashedMaterial({
            color: 0xef4444,
            dashSize: 0.5,
            gapSize: 0.25,
            linewidth: 4,
          });
          const line = new THREE.Line(geo, mat);
          line.computeLineDistances();
          this.scene.add(line);
          this.deadlockCycleLines.push(line);
        }
      });
    }
  }

  setIsometricCamera() {
    this.targetCameraPos = new THREE.Vector3(
      this.gridWidth * this.cellSize * 0.95,
      28,
      this.gridHeight * this.cellSize * 1.35
    );
    this.targetLookAt = new THREE.Vector3(
      (this.gridWidth * this.cellSize) / 2,
      0,
      (this.gridHeight * this.cellSize) / 2
    );
    this.followTargetId = null;
  }

  setTopCamera() {
    this.targetCameraPos = new THREE.Vector3(
      (this.gridWidth * this.cellSize) / 2,
      42,
      (this.gridHeight * this.cellSize) / 2 + 0.1
    );
    this.targetLookAt = new THREE.Vector3(
      (this.gridWidth * this.cellSize) / 2,
      0,
      (this.gridHeight * this.cellSize) / 2
    );
    this.followTargetId = null;
  }

  followRobot(robotId) {
    this.followTargetId = robotId || null;
  }

  focusIncident() {
    // Focus on first failed robot or dynamic obstacle
    for (const [id, mesh] of this.robotMeshes.entries()) {
      if (mesh.userData.statusRing && mesh.userData.statusRing.material.color.getHex() === 0xef4444) {
        this.targetLookAt = mesh.position.clone();
        this.targetCameraPos = mesh.position.clone().add(new THREE.Vector3(8, 12, 10));
        this.followTargetId = null;
        return;
      }
    }
    for (const obs of this.obstacleMeshes.values()) {
      this.targetLookAt = obs.position.clone();
      this.targetCameraPos = obs.position.clone().add(new THREE.Vector3(8, 12, 10));
      this.followTargetId = null;
      return;
    }
    this.setIsometricCamera();
  }

  onResize() {
    if (!this.container || !this.renderer || !this.camera) return;
    const width = this.container.clientWidth;
    const height = this.container.clientHeight;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }

  animate() {
    this.animId = requestAnimationFrame(() => this.animate());

    // Interpolate camera towards target position if set
    if (this.targetCameraPos) {
      this.camera.position.lerp(this.targetCameraPos, 0.08);
      if (this.camera.position.distanceTo(this.targetCameraPos) < 0.1) {
        this.targetCameraPos = null;
      }
    }
    if (this.targetLookAt && !this.followTargetId) {
      this.controls.target.lerp(this.targetLookAt, 0.08);
      if (this.controls.target.distanceTo(this.targetLookAt) < 0.1) {
        this.targetLookAt = null;
      }
    }

    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }

  destroy() {
    if (this.animId) cancelAnimationFrame(this.animId);
    if (this.renderer && this.renderer.domElement) {
      this.renderer.domElement.remove();
    }
    this.initialized = false;
  }
}

// Global hook for dashboard.html
window.DigitalTwin3D = DigitalTwin3D;
