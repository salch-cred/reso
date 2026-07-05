import * as THREE from 'three';

const canvas = document.getElementById('globeCanvas');

if (canvas && window.WebGLRenderingContext) {
  try {
    const wrap = canvas.parentElement;
    let width = wrap.clientWidth || 400;
    let height = wrap.clientHeight || 400;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = 2.6;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height);

    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const sun = new THREE.DirectionalLight(0xffffff, 1.1);
    sun.position.set(5, 3, 5);
    scene.add(sun);

    const globeGroup = new THREE.Group();
    scene.add(globeGroup);

    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin('anonymous');

    const FALLBACK_COLOR = 0x2b3a67;
    const sphereGeo = new THREE.SphereGeometry(1, 64, 64);
    const sphereMat = new THREE.MeshPhongMaterial({ color: FALLBACK_COLOR, shininess: 6 });
    const earth = new THREE.Mesh(sphereGeo, sphereMat);
    globeGroup.add(earth);

    const TEX_BASE = 'https://cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets/';
    loader.load(TEX_BASE + 'earth_atmos_2048.jpg', (tex) => {
      sphereMat.map = tex;
      sphereMat.color.set(0xffffff);
      sphereMat.needsUpdate = true;
    }, undefined, () => {});
    loader.load(TEX_BASE + 'earth_specular_2048.jpg', (tex) => {
      sphereMat.specularMap = tex;
      sphereMat.needsUpdate = true;
    }, undefined, () => {});

    const atmosGeo = new THREE.SphereGeometry(1.035, 64, 64);
    const atmosMat = new THREE.MeshBasicMaterial({ color: 0x4f46e5, transparent: true, opacity: 0.13, side: THREE.BackSide });
    globeGroup.add(new THREE.Mesh(atmosGeo, atmosMat));

    const cities = [
      ['New York', 40.71, -74.0],
      ['London', 51.5, -0.12],
      ['Lagos', 6.45, 3.39],
      ['Dubai', 25.2, 55.27],
      ['Singapore', 1.35, 103.8],
      ['Sao Paulo', -23.55, -46.63],
      ['Sydney', -33.87, 151.2],
      ['Nairobi', -1.29, 36.82],
    ];

    function latLngToVec3(lat, lng, r) {
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lng + 180) * (Math.PI / 180);
      return new THREE.Vector3(
        -r * Math.sin(phi) * Math.cos(theta),
        r * Math.cos(phi),
        r * Math.sin(phi) * Math.sin(theta)
      );
    }

    const markerGeo = new THREE.SphereGeometry(0.016, 10, 10);
    const cityMeshes = cities.map(([name, lat, lng]) => {
      const pos = latLngToVec3(lat, lng, 1.015);
      const mat = new THREE.MeshBasicMaterial({ color: 0x818cf8 });
      const m = new THREE.Mesh(markerGeo, mat);
      m.position.copy(pos);
      globeGroup.add(m);
      return { name, lat, lng, mesh: m };
    });

    function createArc(p1, p2) {
      const mid = p1.clone().add(p2).multiplyScalar(0.5);
      const dist = p1.distanceTo(p2);
      mid.setLength(1 + dist * 0.5);
      const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
      const points = curve.getPoints(64);
      const geo = new THREE.BufferGeometry().setFromPoints(points);
      const mat = new THREE.LineBasicMaterial({ color: 0x6366f1, transparent: true, opacity: 0 });
      const line = new THREE.Line(geo, mat);
      globeGroup.add(line);
      return { line, mat, points, progress: 0, active: false };
    }

    const arcs = [];
    for (let i = 0; i < 7; i++) {
      const a = cityMeshes[Math.floor(Math.random() * cityMeshes.length)];
      let b = cityMeshes[Math.floor(Math.random() * cityMeshes.length)];
      let guard = 0;
      while (b === a && guard++ < 10) b = cityMeshes[Math.floor(Math.random() * cityMeshes.length)];
      arcs.push(Object.assign(createArc(a.mesh.position, b.mesh.position), { from: a, to: b }));
    }

    const pulseGeo = new THREE.SphereGeometry(0.02, 10, 10);
    const pulseMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
    const pulseMesh = new THREE.Mesh(pulseGeo, pulseMat);
    pulseMesh.visible = false;
    globeGroup.add(pulseMesh);

    const feedList = document.getElementById('gfList');
    const proofTypes = [
      'Sanctions proof verified',
      'KYC tier confirmed',
      'Spending limit check passed',
      'Revocation check clear',
      'Settlement confirmed on Stellar',
    ];
    let proofCount = 0;
    const proofsEl = document.getElementById('gStatProofs');
    const citiesEl = document.getElementById('gStatCities');
    if (citiesEl) citiesEl.textContent = String(cities.length);

    function pushFeed(fromName, toName, type) {
      if (!feedList) return;
      const el = document.createElement('div');
      el.className = 'gf-item';
      el.innerHTML = '<i class="hgi-stroke hgi-checkmark-circle-01"></i><span><b>' + type + '</b> &middot; ' + fromName + ' &rarr; ' + toName + '</span>';
      feedList.prepend(el);
      while (feedList.children.length > 6) feedList.removeChild(feedList.lastChild);
      proofCount++;
      if (proofsEl) proofsEl.textContent = String(proofCount);
    }

    function triggerArc() {
      const arc = arcs[Math.floor(Math.random() * arcs.length)];
      arc.active = true;
      arc.progress = 0;
      arc.mat.opacity = 0.9;
      const type = proofTypes[Math.floor(Math.random() * proofTypes.length)];
      pushFeed(arc.from.name, arc.to.name, type);
    }
    const arcInterval = setInterval(triggerArc, 1800);
    triggerArc();

    let isDragging = false, prevX = 0, prevY = 0, autoRotate = true;
    let rotY = 0.4, rotX = 0.2;
    canvas.addEventListener('pointerdown', (e) => { isDragging = true; autoRotate = false; prevX = e.clientX; prevY = e.clientY; });
    window.addEventListener('pointerup', () => { isDragging = false; });
    window.addEventListener('pointermove', (e) => {
      if (!isDragging) return;
      const dx = e.clientX - prevX, dy = e.clientY - prevY;
      rotY += dx * 0.005;
      rotX += dy * 0.005;
      rotX = Math.max(-1, Math.min(1, rotX));
      prevX = e.clientX; prevY = e.clientY;
    });

    const globeSection = document.querySelector('.globe-sec');
    let scrollRot = 0;
    window.addEventListener('scroll', () => {
      if (!globeSection) return;
      const rect = globeSection.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      const progress = 1 - Math.min(Math.max(rect.top / vh, -1), 1);
      scrollRot = progress * 1.2;
    }, { passive: true });

    function resize() {
      width = wrap.clientWidth || width;
      height = wrap.clientHeight || height;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    }
    window.addEventListener('resize', resize);

    const clock = new THREE.Clock();
    function animate() {
      requestAnimationFrame(animate);
      const dt = Math.min(clock.getDelta(), 0.05);
      if (autoRotate) rotY += dt * 0.08;
      globeGroup.rotation.y = rotY + scrollRot;
      globeGroup.rotation.x = rotX * 0.4;

      let anyActive = false;
      arcs.forEach((arc) => {
        if (arc.active) {
          anyActive = true;
          arc.progress += dt * 0.6;
          if (arc.progress >= 1) {
            arc.active = false;
            arc.mat.opacity = 0;
          } else {
            const idx = Math.floor(arc.progress * (arc.points.length - 1));
            pulseMesh.position.copy(arc.points[idx]);
            pulseMesh.visible = true;
          }
        }
      });
      if (!anyActive) pulseMesh.visible = false;

      renderer.render(scene, camera);
    }
    animate();

    window.addEventListener('beforeunload', () => clearInterval(arcInterval));
  } catch (err) {
    console.warn('Globe init failed', err);
  }
}
