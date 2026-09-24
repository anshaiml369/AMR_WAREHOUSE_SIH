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
    this.rackMeshes = new Map();
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
    this.raycaster = new THREE.Raycaster();
    this.mouse = new THREE.Vector2();
  }

  init() {
    if (this.initialized || !this.container) return;

    const width = this.container.clientWidth || 800;
    const height = this.container.clientHeight || 540;

    // 1. Scene - Sophisticated White / Glass / Crystal Industrial Environment
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xf8fafc);
    this.scene.fog = new THREE.FogExp2(0xf8fafc, 0.0035);

    // 2. Camera
    this.camera = new THREE.PerspectiveCamera(45, width / height, 0.5, 500);
    this.setIsometricCamera();

    // 3. Renderer with soft shadows & crisp filmlike tone mapping
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setSize(width, height);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.container.appendChild(this.renderer.domElement);

    // 4. OrbitControls
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.05; // Stay above ground plane
    this.controls.minDistance = 6;
    this.controls.maxDistance = 140;
    this.controls.target.set(
      (this.gridWidth * this.cellSize) / 2,
      0,
      (this.gridHeight * this.cellSize) / 2
    );

    // 5. Lighting - Natural Clean Daylight + Crystal Fill
    this.setupLighting();

    // 6. Floor & Static Grid Structure - Crystalline White Epoxy Floor
    this.createWarehouseEnvironment();

    // 7. Click raycasting for AMR and Rack selection
    this.renderer.domElement.addEventListener('click', (e) => this.onCanvasClick(e));
    window.addEventListener('resize', () => this.onResize());

    this.initialized = true;
    this.animate();
  }

  setupLighting() {
    // Pure Clean White Ambient Fill
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.1);
    this.scene.add(ambientLight);

    // Main Overhead Daylight Sun
    const mainSun = new THREE.DirectionalLight(0xffffff, 1.2);
    mainSun.position.set(35, 55, 30);
    mainSun.castShadow = true;
    mainSun.shadow.mapSize.width = 2048;
    mainSun.shadow.mapSize.height = 2048;
    mainSun.shadow.camera.near = 10;
    mainSun.shadow.camera.far = 130;
    const d = 34;
    mainSun.shadow.camera.left = -d;
    mainSun.shadow.camera.right = d;
    mainSun.shadow.camera.top = d;
    mainSun.shadow.camera.bottom = -d;
    mainSun.shadow.bias = -0.0005;
    this.scene.add(mainSun);

    // Subtle Icy Blue Crystal Skylight Fill
    const crystalFill = new THREE.DirectionalLight(0xe0f2fe, 0.45);
    crystalFill.position.set(-30, 40, -30);
    this.scene.add(crystalFill);
  }

  createWarehouseEnvironment() {
    const totalW = this.gridWidth * this.cellSize;
    const totalH = this.gridHeight * this.cellSize;

    // Floor: White Translucent High-Reflectance Epoxy / Polished Crystal Slab
    const floorGeo = new THREE.PlaneGeometry(totalW, totalH);
    const floorMat = new THREE.MeshStandardMaterial({
      color: 0xfcfdfd,
      roughness: 0.12,
      metalness: 0.05,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.set(totalW / 2, 0, totalH / 2);
    floor.receiveShadow = true;
    this.scene.add(floor);

    // Grid: Subtle Slate Guidelines with Crystal Primary Divisions
    const gridHelper = new THREE.GridHelper(totalW, this.gridWidth, 0x0284c7, 0xe2e8f0);
    gridHelper.position.set(totalW / 2, 0.02, totalH / 2);
    this.scene.add(gridHelper);

    // Outer Perimeter Guardrails: Brushed Aluminum Posts with Frosted Glass Panels
    const railMat = new THREE.MeshStandardMaterial({
      color: 0xcbd5e1,
      metalness: 0.4,
      roughness: 0.25,
    });
    const glassMat = new THREE.MeshPhysicalMaterial({
      color: 0xe0f2fe,
      transmission: 0.65,
      opacity: 0.5,
      transparent: true,
      roughness: 0.15,
      metalness: 0.05,
    });

    const railHeight = 0.75;
    const railThick = 0.15;

    // Perimeter borders
    const borders = [
      { w: totalW, h: railHeight, d: railThick, x: totalW / 2, y: railHeight / 2, z: 0 },
      { w: totalW, h: railHeight, d: railThick, x: totalW / 2, y: railHeight / 2, z: totalH },
      { w: railThick, h: railHeight, d: totalH, x: 0, y: railHeight / 2, z: totalH / 2 },
      { w: railThick, h: railHeight, d: totalH, x: totalW, y: railHeight / 2, z: totalH / 2 },
    ];

    borders.forEach(b => {
      const rail = new THREE.Mesh(new THREE.BoxGeometry(b.w, b.h, b.d), glassMat);
      rail.position.set(b.x, b.y, b.z);
      this.scene.add(rail);

      const topTrim = new THREE.Mesh(new THREE.BoxGeometry(b.w, 0.06, b.d + 0.04), railMat);
      topTrim.position.set(b.x, b.h, b.z);
      this.scene.add(topTrim);
    });
  }

  cellToWorld(x, y) {
    return new THREE.Vector3((x + 0.5) * this.cellSize, 0, (y + 0.5) * this.cellSize);
  }

  update(data) {
    if (!this.initialized) {
      this.init();
    }
    if (!data) return;

    if (data.warehouse && data.warehouse.width) {
      this.gridWidth = data.warehouse.width;
      this.gridHeight = data.warehouse.height;
    }

    this.updateRacks(data);
    this.updateChargingStations(data);
    this.updateRobots(data.robots || []);
    this.updateDynamicObstacles(data.dynamic_blockages || []);
    this.updateNegotiationBeams(data.robots || []);
    this.updateDeadlockVisuals(data.wfg_cycles || []);

    // Smooth follow-camera
    if (this.followTargetId) {
      const mesh = this.robotMeshes.get(this.followTargetId);
      if (mesh) {
        this.controls.target.lerp(mesh.position, 0.08);
      }
    }
  }

  updateRacks(data) {
    const racks = (data.warehouse && data.warehouse.racks) || data.racks || [];
    const activeRackIds = new Set();

    if (racks.length > 0) {
      racks.forEach(rack => {
        const id = rack.id || rack.rack_id;
        activeRackIds.add(id);
        let mesh = this.rackMeshes.get(id);
        if (!mesh) {
          mesh = this.createMultiCellRackMesh(rack);
          this.rackMeshes.set(id, mesh);
          this.scene.add(mesh);
        } else {
          // If rack moved or resized, update position
          const expectedPos = this.getRackCenterWorld(rack);
          if (mesh.position.distanceTo(expectedPos) > 0.01) {
            this.scene.remove(mesh);
            mesh = this.createMultiCellRackMesh(rack);
            this.rackMeshes.set(id, mesh);
            this.scene.add(mesh);
          }
        }
      });
    } else {
      // Fallback: render individual static obstacle cells
      const obstacles = (data.warehouse && data.warehouse.obstacles) || data.obstacles || [];
      obstacles.forEach(([x, y]) => {
        if (x === 0 || x === this.gridWidth - 1 || y === 0 || y === this.gridHeight - 1) return;
        const key = `static_${x}_${y}`;
        activeRackIds.add(key);
        if (!this.rackMeshes.has(key)) {
          const pseudoRack = { id: key, x, y, width: 1, height: 1, span_x: 1, span_y: 1, rack_type: 'small', tiers: 3 };
          const mesh = this.createMultiCellRackMesh(pseudoRack);
          this.rackMeshes.set(key, mesh);
          this.scene.add(mesh);
        }
      });
    }

    // Clean up removed racks
    for (const [id, mesh] of this.rackMeshes.entries()) {
      if (!activeRackIds.has(id)) {
        this.scene.remove(mesh);
        this.rackMeshes.delete(id);
      }
    }
  }

  getRackCenterWorld(rack) {
    const spanX = rack.span_x || rack.width || 1;
    const spanY = rack.span_y || rack.height || 1;
    const cx = (rack.x + spanX / 2) * this.cellSize;
    const cz = (rack.y + spanY / 2) * this.cellSize;
    return new THREE.Vector3(cx, 0, cz);
  }

  createMultiCellRackMesh(rack) {
    const group = new THREE.Group();
    const spanX = (rack.span_x || rack.width || 1) * this.cellSize;
    const spanZ = (rack.span_y || rack.height || 1) * this.cellSize;
    const tiers = rack.tiers || (rack.rack_type === 'large' ? 4 : rack.rack_type === 'small' ? 2 : 3);
    const rackHeight = tiers * 0.55 + 0.2;

    const center = this.getRackCenterWorld(rack);
    group.position.copy(center);
    group.userData = { type: 'rack', rackId: rack.id || rack.rack_id, rackData: rack };

    // 1. Crystal White / Brushed Platinum Structural Posts
    const postMat = new THREE.MeshStandardMaterial({
      color: 0xe2e8f0,
      metalness: 0.4,
      roughness: 0.2,
    });
    const postRadius = 0.06;
    const postGeo = new THREE.CylinderGeometry(postRadius, postRadius, rackHeight, 12);

    const halfW = spanX / 2 - 0.15;
    const halfZ = spanZ / 2 - 0.15;
    const postPositions = [
      [-halfW, -halfZ],
      [halfW, -halfZ],
      [-halfW, halfZ],
      [halfW, halfZ],
    ];

    // Add intermediate posts for large spans
    if (spanX > 4.0) {
      postPositions.push([0, -halfZ], [0, halfZ]);
    }
    if (spanZ > 4.0) {
      postPositions.push([-halfW, 0], [halfW, 0]);
    }

    postPositions.forEach(([px, pz]) => {
      const p = new THREE.Mesh(postGeo, postMat);
      p.position.set(px, rackHeight / 2, pz);
      p.castShadow = true;
      group.add(p);
    });

    // 2. Frosted Glass / Clear Crystal Shelving Tiers
    const shelfGeo = new THREE.BoxGeometry(spanX - 0.1, 0.04, spanZ - 0.1);
    const glassShelfMat = new THREE.MeshPhysicalMaterial({
      color: 0xf0fdfa,
      transmission: 0.7,
      opacity: 0.65,
      transparent: true,
      roughness: 0.15,
      metalness: 0.05,
    });

    const tierStep = (rackHeight - 0.2) / tiers;
    for (let t = 1; t <= tiers; t++) {
      const sy = t * tierStep;
      const shelf = new THREE.Mesh(shelfGeo, glassShelfMat);
      shelf.position.set(0, sy, 0);
      shelf.receiveShadow = true;
      group.add(shelf);

      // Industrial Totes on this tier
      this.populateTierTotes(group, spanX, spanZ, sy, t, rack.rack_type);
    }

    return group;
  }

  populateTierTotes(group, spanX, spanZ, shelfY, tierIdx, rackType) {
    const toteColors = [
      0x0284c7, // Crystal Ice Cyan
      0xf59e0b, // Warm Amber
      0xe2e8f0, // Platinum Slate
      0x06b6d4, // Cyan
    ];

    const toteW = 0.55;
    const toteH = 0.32;
    const toteD = 0.55;
    const toteGeo = new THREE.BoxGeometry(toteW, toteH, toteD);

    const cols = Math.max(1, Math.floor((spanX - 0.4) / (toteW + 0.15)));
    const rows = Math.max(1, Math.floor((spanZ - 0.4) / (toteD + 0.15)));

    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        // Skip occasional slots to look authentic
        if ((r + c + tierIdx) % 7 === 0) continue;

        const color = toteColors[(c * 3 + r * 2 + tierIdx) % toteColors.length];
        const toteMat = new THREE.MeshStandardMaterial({
          color,
          roughness: 0.35,
          metalness: 0.1,
        });

        const tote = new THREE.Mesh(toteGeo, toteMat);
        const xOffset = -((cols - 1) * 0.7) / 2 + c * 0.7;
        const zOffset = -((rows - 1) * 0.7) / 2 + r * 0.7;
        tote.position.set(xOffset, shelfY + toteH / 2 + 0.02, zOffset);
        tote.castShadow = true;
        group.add(tote);
      }
    }
  }

  updateChargingStations(data) {
    const stations = (data.warehouse && data.warehouse.charging_stations) || data.charging_stations || [];
    const activeKeys = new Set();

    stations.forEach(([x, y]) => {
      const key = `${x},${y}`;
      activeKeys.add(key);
      if (!this.dockMeshes.has(key)) {
        const dock = this.createChargingDockMesh(x, y);
        this.dockMeshes.set(key, dock);
        this.scene.add(dock);
      }
    });

    for (const [key, mesh] of this.dockMeshes.entries()) {
      if (!activeKeys.has(key)) {
        this.scene.remove(mesh);
        this.dockMeshes.delete(key);
      }
    }
  }

  createChargingDockMesh(x, y) {
    const group = new THREE.Group();
    const pos = this.cellToWorld(x, y);
    group.position.copy(pos);

    // 1. Crystal Emerald Charging Bay Induction Pad
    const padGeo = new THREE.BoxGeometry(1.6, 0.05, 1.6);
    const padMat = new THREE.MeshStandardMaterial({
      color: 0xecfdf5,
      emissive: 0x10b981,
      emissiveIntensity: 0.3,
      metalness: 0.1,
      roughness: 0.3,
    });
    const pad = new THREE.Mesh(padGeo, padMat);
    pad.position.y = 0.025;
    pad.receiveShadow = true;
    group.add(pad);

    // 2. Sleek Vertical White Crystal Charger Monolith
    const towerGeo = new THREE.BoxGeometry(0.3, 1.4, 0.3);
    const towerMat = new THREE.MeshStandardMaterial({
      color: 0xf1f5f9,
      metalness: 0.3,
      roughness: 0.25,
    });
    const tower = new THREE.Mesh(towerGeo, towerMat);
    tower.position.set(0, 0.7, -0.65);
    tower.castShadow = true;
    group.add(tower);

    // 3. Status Beacon Sphere
    const beaconGeo = new THREE.SphereGeometry(0.12, 16, 16);
    const beaconMat = new THREE.MeshBasicMaterial({ color: 0x10b981 });
    const beacon = new THREE.Mesh(beaconGeo, beaconMat);
    beacon.position.set(0, 1.35, -0.65);
    group.add(beacon);

    return group;
  }

  createAMRMesh(robot) {
    const group = new THREE.Group();
    group.userData = { type: 'amr', robotId: robot.robot_id };

    // 1. Authentic Industrial Chassis: Low-profile durable slate/platinum body
    const bodyGeo = new THREE.CylinderGeometry(0.64, 0.68, 0.3, 24);
    const bodyMat = new THREE.MeshStandardMaterial({
      color: 0xcbd5e1, // Industrial Platinum Slate (high contrast against white floor)
      metalness: 0.3,
      roughness: 0.35,
    });
    const body = new THREE.Mesh(bodyGeo, bodyMat);
    body.position.y = 0.22;
    body.castShadow = true;
    body.receiveShadow = true;
    group.add(body);

    // Dark Lower Perimeter Protective Bumper
    const skirtGeo = new THREE.CylinderGeometry(0.68, 0.7, 0.1, 24);
    const skirtMat = new THREE.MeshStandardMaterial({
      color: 0x1e293b,
      roughness: 0.8,
    });
    const skirt = new THREE.Mesh(skirtGeo, skirtMat);
    skirt.position.y = 0.1;
    group.add(skirt);

    // 2. Heavy-Duty Polyurethane Drive Wheels (Dark Rubber)
    const wheelGeo = new THREE.CylinderGeometry(0.17, 0.17, 0.08, 16);
    const wheelMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, roughness: 0.9 });
    const leftWheel = new THREE.Mesh(wheelGeo, wheelMat);
    leftWheel.rotation.z = Math.PI / 2;
    leftWheel.position.set(-0.64, 0.17, 0);
    group.add(leftWheel);

    const rightWheel = new THREE.Mesh(wheelGeo, wheelMat);
    rightWheel.rotation.z = Math.PI / 2;
    rightWheel.position.set(0.64, 0.17, 0);
    group.add(rightWheel);

    // 3. Top Rotating Turntable / Cargo Lift Plate
    const liftGeo = new THREE.CylinderGeometry(0.44, 0.44, 0.04, 24);
    const liftMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.5, roughness: 0.3 });
    const liftPlate = new THREE.Mesh(liftGeo, liftMat);
    liftPlate.position.y = 0.38;
    group.add(liftPlate);

    // 4. Center 360° Safety LiDAR Scanner Puck (Dark Optical Sensor)
    const lidarGeo = new THREE.CylinderGeometry(0.13, 0.13, 0.1, 16);
    const lidarMat = new THREE.MeshStandardMaterial({
      color: 0x0f172a,
      metalness: 0.8,
      roughness: 0.2,
    });
    const lidar = new THREE.Mesh(lidarGeo, lidarMat);
    lidar.position.set(0, 0.44, 0);
    group.add(lidar);

    // 5. Restrained High-Visibility Status Indicator Ring (Green = Moving, Amber = Negotiating, Red = Fault)
    const ringGeo = new THREE.TorusGeometry(0.64, 0.03, 8, 32);
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x10b981 });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.22;
    group.add(ring);
    group.userData.statusRing = ring;

    // 6. Cargo Tote Container (when carrying)
    const cargoGeo = new THREE.BoxGeometry(0.65, 0.48, 0.65);
    const cargoMat = new THREE.MeshStandardMaterial({
      color: 0xf59e0b,
      roughness: 0.4,
      metalness: 0.1,
    });
    const cargo = new THREE.Mesh(cargoGeo, cargoMat);
    cargo.position.set(0, 0.65, 0);
    cargo.castShadow = true;
    cargo.visible = false;
    group.add(cargo);
    group.userData.cargoMesh = cargo;

    // 7. Frosted Crystal Billboard Label (High Contrast Typography)
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

      // Target position for 60 FPS lerping
      const targetPos = this.cellToWorld(r.position[0], r.position[1]);
      mesh.userData.targetPosition = targetPos;

      // Orientation calculation
      if (r.path && r.path.length > 1) {
        const nextCell = r.path[1];
        const nextPos = this.cellToWorld(nextCell[0], nextCell[1]);
        const dir = nextPos.clone().sub(mesh.position);
        if (dir.lengthSq() > 0.001) {
          mesh.userData.targetRotationY = Math.atan2(dir.x, dir.z);
        }
      }

      // Restrained status ring
      const ring = mesh.userData.statusRing;
      if (ring) {
        let colorHex = 0x0284c7; // Idle crystal blue
        if (r.failed || r.state === 'FAILED') colorHex = 0xef4444; // Red
        else if (r.state.startsWith('DOCK') || r.state === 'CHARGING') colorHex = 0x10b981; // Green
        else if (r.state === 'WAITING' || r.state === 'NEGOTIATING') colorHex = 0xf59e0b; // Amber
        else if (r.carrying_package_id) colorHex = 0x0284c7; // Blue
        else if (r.state.startsWith('MOVING')) colorHex = 0x10b981; // Emerald
        ring.material.color.setHex(colorHex);
      }

      // Cargo Box visibility
      const cargo = mesh.userData.cargoMesh;
      if (cargo) {
        cargo.visible = Boolean(r.carrying_package_id);
      }

      this.updateRobotLabel(mesh, r);
      this.updateRobotPathLine(r);
    });
  }

  updateRobotLabel(mesh, r) {
    const canvas = mesh.userData.labelCanvas;
    const texture = mesh.userData.labelTexture;
    if (!canvas || !texture) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Frosted Crystal Capsule with crisp border
    ctx.fillStyle = 'rgba(255, 255, 255, 0.94)';
    ctx.strokeStyle = r.failed ? '#ef4444' : '#0284c7';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.roundRect(6, 6, canvas.width - 12, canvas.height - 12, 12);
    ctx.fill();
    ctx.stroke();

    // High-Contrast Dark Typography
    const speedMult = (r.speed_multiplier !== undefined ? Number(r.speed_multiplier) : 1.0).toFixed(1);
    ctx.font = 'bold 22px Inter, sans-serif';
    ctx.fillStyle = '#0f172a';
    ctx.fillText(`${r.robot_id} [${speedMult}x]`, 16, 32);

    // Battery / State
    ctx.font = 'bold 16px Inter, sans-serif';
    ctx.fillStyle = r.battery < 25 ? '#dc2626' : '#059669';
    const targetStr = (r.target_tasks !== undefined && r.target_tasks !== null) ? ` (${r.assigned_tasks_count || 0}/${r.target_tasks})` : '';
    ctx.fillText(`⚡${Math.round(r.battery)}% [${r.state}]${targetStr}`, 16, 58);

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
        color: r.carrying_package_id ? 0xf59e0b : 0x0284c7,
        linewidth: 3,
        transparent: true,
        opacity: 0.8,
      });
      line = new THREE.Line(geometry, material);
      this.scene.add(line);
      this.pathLines.set(r.robot_id, line);
    } else {
      line.geometry.dispose();
      line.geometry = geometry;
      line.material.color.setHex(r.carrying_package_id ? 0xf59e0b : 0x0284c7);
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
        const obsGeo = new THREE.BoxGeometry(1.5, 1.0, 1.5);
        const obsMat = new THREE.MeshStandardMaterial({
          color: 0xef4444,
          roughness: 0.35,
          metalness: 0.2,
        });
        const obs = new THREE.Mesh(obsGeo, obsMat);
        const pos = this.cellToWorld(x, y);
        obs.position.set(pos.x, 0.5, pos.z);
        obs.castShadow = true;
        this.scene.add(obs);
        this.obstacleMeshes.set(key, obs);
      }
    });
  }

  updateNegotiationBeams(robots) {
    this.negotiationBeams.forEach(b => this.scene.remove(b));
    this.negotiationBeams = [];

    const negotiatingRobots = robots.filter(r => r.state === 'NEGOTIATING');
    if (negotiatingRobots.length >= 2) {
      for (let i = 0; i < negotiatingRobots.length - 1; i++) {
        const r1 = negotiatingRobots[i];
        const r2 = negotiatingRobots[i + 1];
        const p1 = this.cellToWorld(r1.position[0], r1.position[1]);
        const p2 = this.cellToWorld(r2.position[0], r2.position[1]);
        p1.y = 0.35;
        p2.y = 0.35;

        const lineGeo = new THREE.BufferGeometry().setFromPoints([p1, p2]);
        const lineMat = new THREE.LineBasicMaterial({ color: 0xf59e0b, linewidth: 3 });
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
            pt.y = 0.45;
            points.push(pt);
          }
        });
        if (points.length >= 2) {
          points.push(points[0].clone());
          const geo = new THREE.BufferGeometry().setFromPoints(points);
          const mat = new THREE.LineDashedMaterial({
            color: 0xef4444,
            dashSize: 0.5,
            gapSize: 0.25,
            linewidth: 3,
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
      this.gridWidth * this.cellSize * 0.92,
      26,
      this.gridHeight * this.cellSize * 1.3
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
      40,
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
    for (const [id, mesh] of this.robotMeshes.entries()) {
      if (mesh.userData.statusRing && mesh.userData.statusRing.material.color.getHex() === 0xef4444) {
        this.targetLookAt = mesh.position.clone();
        this.targetCameraPos = mesh.position.clone().add(new THREE.Vector3(8, 10, 10));
        this.followTargetId = null;
        return;
      }
    }
    this.setIsometricCamera();
  }

  onCanvasClick(event) {
    if (!this.container || !this.camera) return;
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

    this.raycaster.setFromCamera(this.mouse, this.camera);
    const intersects = this.raycaster.intersectObjects(this.scene.children, true);

    for (const hit of intersects) {
      let obj = hit.object;
      while (obj && obj !== this.scene) {
        if (obj.userData && obj.userData.type === 'rack') {
          if (typeof window.selectRack === 'function') {
            window.selectRack(obj.userData.rackId, obj.userData.rackData);
          }
          return;
        }
        if (obj.userData && obj.userData.type === 'amr') {
          if (typeof window.selectRobot === 'function') {
            window.selectRobot(obj.userData.robotId);
          }
          return;
        }
        obj = obj.parent;
      }
    }
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

    // 60 FPS lerping for all robots
    for (const mesh of this.robotMeshes.values()) {
      if (mesh.userData.targetPosition) {
        mesh.position.lerp(mesh.userData.targetPosition, 0.18);
      }
      if (mesh.userData.targetRotationY !== undefined) {
        mesh.rotation.y = THREE.MathUtils.lerp(mesh.rotation.y, mesh.userData.targetRotationY, 0.18);
      }
    }

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

window.DigitalTwin3D = DigitalTwin3D;
