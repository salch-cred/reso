const canvas = document.getElementById('globeCanvas');
const section = document.querySelector('.globe-sec');

function prefersReducedMotion() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

if (canvas && section && window.WebGLRenderingContext) {
  let launched = false;
  const launchObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting && !launched) {
        launched = true;
        launchObserver.disconnect();
        import('three')
          .then((THREE) => initGlobe(THREE))
          .catch((err) => console.warn('Globe failed to load', err));
      }
    });
  }, { rootMargin: '250px 0px' });
  launchObserver.observe(section);
}

function initGlobe(THREE) {
  try {
    const wrap = canvas.parentElement;
    const isSmall = window.innerWidth < 700;
    const reduced = prefersReducedMotion();
    let width = wrap.clientWidth || 400;
    let height = wrap.clientHeight || 400;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000);
    camera.position.z = isSmall ? 3.1 : 3.6;

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: !isSmall, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, isSmall ? 1.5 : 2));
    renderer.setSize(width, height);

    scene.add(new THREE.AmbientLight(0xffffff, 0.75));
    const sun = new THREE.DirectionalLight(0xffffff, 1.1);
    sun.position.set(5, 3, 5);
    scene.add(sun);

    // starfield backdrop
    const starCount = isSmall ? 450 : 1300;
    const starGeo = new THREE.BufferGeometry();
    const starPos = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount; i++) {
      const r = 6 + Math.random() * 6;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(Math.random() * 2 - 1);
      starPos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      starPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      starPos[i * 3 + 2] = r * Math.cos(phi);
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starPos, 3));
    const starMat = new THREE.PointsMaterial({ color: 0xc7d2fe, size: 0.022, transparent: true, opacity: 0.75 });
    const stars = new THREE.Points(starGeo, starMat);
    scene.add(stars);

    const globeGroup = new THREE.Group();
    scene.add(globeGroup);

    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin('anonymous');

    const segs = isSmall ? 40 : 64;
    const sphereGeo = new THREE.SphereGeometry(1, segs, segs);
    const sphereMat = new THREE.MeshPhongMaterial({ color: 0x2b3a67, shininess: 6 });
    const earth = new THREE.Mesh(sphereGeo, sphereMat);
    globeGroup.add(earth);

    const TEX_BASE = 'https://cdn.jsdelivr.net/gh/mrdoob/three.js@r160/examples/textures/planets/';
    loader.load(TEX_BASE + 'earth_atmos_2048.jpg', (tex) => {
      sphereMat.map = tex;
      sphereMat.color.set(0xffffff);
      sphereMat.needsUpdate = true;
    });
    loader.load(TEX_BASE + 'earth_specular_2048.jpg', (tex) => {
      sphereMat.specularMap = tex;
      sphereMat.needsUpdate = true;
    });

    const atmosGeo = new THREE.SphereGeometry(1.03, segs, segs);
    const atmosMat = new THREE.MeshBasicMaterial({ color: 0x4f46e5, transparent: true, opacity: 0.12, side: THREE.BackSide });
    globeGroup.add(new THREE.Mesh(atmosGeo, atmosMat));

    // fresnel rim glow for extra 3D depth
    const fresnelMat = new THREE.ShaderMaterial({
      uniforms: { glowColor: { value: new THREE.Color(0x6366f1) } },
      vertexShader: [
        'varying float intensity;',
        'void main() {',
        '  vec3 vN = normalize( normalMatrix * normal );',
        '  vec3 vNel = normalize( normalMatrix * vec3(0.0, 0.0, 1.0) );',
        '  intensity = pow( 0.62 - dot(vN, vNel), 2.8 );',
        '  gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );',
        '}',
      ].join('\n'),
      fragmentShader: [
        'uniform vec3 glowColor;',
        'varying float intensity;',
        'void main() {',
        '  gl_FragColor = vec4( glowColor, 1.0 ) * intensity;',
        '}',
      ].join('\n'),
      side: THREE.BackSide,
      blending: THREE.AdditiveBlending,
      transparent: true,
    });
    const fresnelMesh = new THREE.Mesh(new THREE.SphereGeometry(1.2, segs, segs), fresnelMat);
    globeGroup.add(fresnelMesh);

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
      const points = curve.getPoints(isSmall ? 40 : 64);
      const geo = new THREE.BufferGeometry().setFromPoints(points);
      const mat = new THREE.LineBasicMaterial({ color: 0x6366f1, transparent: true, opacity: 0 });
      const line = new THREE.Line(geo, mat);
      globeGroup.add(line);
      return { line, mat, points, progress: 0, active: false };
    }

    const arcCount = isSmall ? 4 : 7;
    const arcs = [];
    for (let i = 0; i < arcCount; i++) {
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
    const arcInterval = setInterval(triggerArc, isSmall ? 2400 : 1800);
    triggerArc();

    let isDragging = false;
    let prevX = 0;
    let prevY = 0;
    let autoRotate = !reduced;
    let rotY = 0.4;
    let rotX = 0.2;
    let parallaxX = 0;
    let parallaxY = 0;

    canvas.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'touch') return;
      isDragging = true;
      autoRotate = false;
      prevX = e.clientX;
      prevY = e.clientY;
    });
    window.addEventListener('pointerup', () => { isDragging = false; });
    window.addEventListener('pointermove', (e) => {
      if (isDragging) {
        const dx = e.clientX - prevX;
        const dy = e.clientY - prevY;
        rotY += dx * 0.005;
        rotX += dy * 0.005;
        rotX = Math.max(-1, Math.min(1, rotX));
        prevX = e.clientX;
        prevY = e.clientY;
        return;
      }
      if (isSmall) return;
      const rect = wrap.getBoundingClientRect();
      if (e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
        parallaxY = ((e.clientX - rect.left) / rect.width - 0.5) * 0.25;
        parallaxX = ((e.clientY - rect.top) / rect.height - 0.5) * 0.15;
      }
    });

    let scrollRot = 0;
    window.addEventListener('scroll', () => {
      const rect = section.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      const progress = 1 - Math.min(Math.max(rect.top / vh, -1), 1);
      scrollRot = progress * 1.2;
      const visibleRatio = Math.min(Math.max((vh - rect.top) / vh, 0), 1);
      camera.position.z = (isSmall ? 3.1 : 3.6) - visibleRatio * (isSmall ? 0.5 : 0.7);
    }, { passive: true });

    function resize() {
      width = wrap.clientWidth || width;
      height = wrap.clientHeight || height;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    }
    let resizeTimer = null;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(resize, 120);
    });

    let running = true;
    let rafId = null;
    const pauseObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        running = entry.isIntersecting;
        if (running && rafId === null) animate();
      });
    }, { rootMargin: '150px 0px' });
    pauseObserver.observe(section);

    const clock = new THREE.Clock();
    function animate() {
      if (!running) { rafId = null; return; }
      rafId = requestAnimationFrame(animate);
      const dt = Math.min(clock.getDelta(), 0.05);
      if (autoRotate) rotY += dt * 0.08;
      globeGroup.rotation.y = rotY + scrollRot + parallaxY;
      globeGroup.rotation.x = rotX * 0.4 + parallaxX;
      stars.rotation.y += dt * 0.01;

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

    window.addEventListener('beforeunload', () => {
      clearInterval(arcInterval);
      if (rafId) cancelAnimationFrame(rafId);
    });
  } catch (err) {
    console.warn('Globe init failed', err);
  }
}
