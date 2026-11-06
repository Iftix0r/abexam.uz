// Abjon's 3D body. The walking, leaping and talking logic lives in
// templates/partials/abjon.html; this draws him from root.dataset.state and
// the values read() returns. If this file or WebGL fails, the page keeps the SVG.
import * as THREE from './vendor/three.module.min.js';

const SKIN = new THREE.Color(0xd9352f);
const LIMB = new THREE.Color(0xb71c1c);
const HOT = new THREE.Color(0xffc21a);
const INK = 0x1c1d24;
const VIEW = 5;  // world units across the canvas
const FIG_PX = 84;  // the --abj-size the jump heights below were tuned for

const damp = (from, to, rate, dt) => from + (to - from) * (1 - Math.exp(-rate * dt));
const ease = t => t * t * (3 - 2 * t);
const clamp01 = t => Math.min(1, Math.max(0, t));

function paint(width, height, draw) {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  draw(canvas.getContext('2d'), width, height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

// The Chust do'ppi: black, with a white pepper motif on each of its four sides.
function doppiTexture() {
  return paint(1024, 256, (c, w, h) => {
    c.fillStyle = '#1c1d24';
    c.fillRect(0, 0, w, h);
    const pepper = (x, size) => {
      c.fillStyle = '#fff';
      c.beginPath();
      c.moveTo(x, h * 0.3);
      c.bezierCurveTo(x + size, h * 0.42, x + size, h * 0.62, x, h * 0.8);
      c.bezierCurveTo(x - size, h * 0.62, x - size, h * 0.42, x, h * 0.3);
      c.fill();
      c.strokeStyle = '#1c1d24';
      c.lineWidth = 6;
      c.beginPath();
      c.moveTo(x, h * 0.42);
      c.lineTo(x, h * 0.7);
      c.stroke();
    };
    for (let i = 0; i < 8; i++) {
      const size = i % 2 ? 22 : 40;
      const x = w * (i / 8);
      pepper(x, size);
      if (i === 0) pepper(w, size);
    }
    c.fillStyle = '#fff';
    for (let x = 6; x < w; x += 22) c.fillRect(x, h * 0.9, 11, 7);
  });
}

function badgeTexture() {
  return paint(256, 256, (c, w, h) => {
    c.fillStyle = '#d32f2f';
    c.beginPath();
    c.arc(w / 2, h / 2, w / 2 - 4, 0, Math.PI * 2);
    c.fill();
    c.fillStyle = '#fff';
    c.font = '700 120px Inter, system-ui, sans-serif';
    c.textAlign = 'center';
    c.textBaseline = 'middle';
    c.fillText('AB', w / 2, h / 2 + 6);
  });
}

function build() {
  const skin = new THREE.MeshStandardMaterial({ color: SKIN.clone(), roughness: 0.42 });
  const limb = new THREE.MeshStandardMaterial({ color: LIMB.clone(), roughness: 0.5 });
  const ink = new THREE.MeshStandardMaterial({ color: INK, roughness: 0.55 });
  const white = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.3 });
  const gloss = new THREE.MeshStandardMaterial({ color: 0x14151a, roughness: 0.15 });
  const mouthMat = new THREE.MeshStandardMaterial({ color: 0x5a0f0f, roughness: 0.6 });
  const blush = new THREE.MeshStandardMaterial({ color: 0xffb4a2, roughness: 0.7 });
  const mesh = (geometry, material, parent, x = 0, y = 0, z = 0) => {
    const m = new THREE.Mesh(geometry, material);
    m.position.set(x, y, z);
    parent.add(m);
    return m;
  };

  const yaw = new THREE.Group();
  const tumble = new THREE.Group();
  const fig = new THREE.Group();
  yaw.add(tumble);
  tumble.add(fig);

  const ball = new THREE.SphereGeometry(1, 48, 32);
  const small = new THREE.SphereGeometry(1, 20, 14);
  mesh(ball, skin, fig).scale.set(1, 1.02, 0.96);

  // Face.
  const eyes = new THREE.Group();
  const pupils = new THREE.Group();
  fig.add(eyes);
  eyes.add(pupils);
  for (const side of [-1, 1]) {
    mesh(small, white, eyes, side * 0.33, 0.14, 0.82).scale.set(0.29, 0.29, 0.1);
    mesh(small, gloss, pupils, side * 0.32, 0.13, 0.9).scale.set(0.15, 0.15, 0.035);
    mesh(small, white, pupils, side * 0.32 + 0.06, 0.2, 0.93).scale.set(0.045, 0.045, 0.02);
    mesh(small, blush, fig, side * 0.6, -0.16, 0.74).scale.set(0.14, 0.11, 0.04);
  }
  const tube = (x1, y1, x2, y2) => new THREE.TubeGeometry(new THREE.QuadraticBezierCurve3(
    new THREE.Vector3(x1, y1, 0.92), new THREE.Vector3(0, y2, 1.0), new THREE.Vector3(-x1, y1, 0.92)
  ), 16, 0.036, 8);
  const smile = mesh(tube(-0.24, -0.26, 0, -0.46), mouthMat, fig);
  const frown = mesh(tube(-0.24, -0.42, 0, -0.26), mouthMat, fig);
  const open = new THREE.Group();
  fig.add(open);
  mesh(small, mouthMat, open, 0, -0.34, 0.9).scale.set(0.2, 0.17, 0.08);
  mesh(small, new THREE.MeshStandardMaterial({ color: 0xff8a80 }), open, 0, -0.42, 0.93).scale.set(0.12, 0.07, 0.05);
  const brows = [-1, 1].map(side => {
    const brow = mesh(new THREE.BoxGeometry(0.5, 0.11, 0.1), ink, fig, side * 0.32, 0.4, 0.9);
    brow.rotation.z = side * 0.5;  // inner ends down: a scowl
    return brow;
  });

  // Do'ppi. A half sphere maps the whole texture onto the cap.
  const cap = mesh(
    new THREE.SphereGeometry(1, 40, 20, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshStandardMaterial({ map: doppiTexture(), roughness: 0.6 }), fig, 0, 0.5, -0.02
  );
  cap.scale.set(0.8, 0.72, 0.8);
  cap.rotation.z = -0.1;

  // Backpack, so the back has something to show.
  const bag = new THREE.Group();
  bag.position.set(0, -0.08, -0.84);
  fig.add(bag);
  mesh(ball, ink, bag).scale.set(0.66, 0.72, 0.34);
  mesh(ball, limb, bag, 0, -0.3, -0.2).scale.set(0.42, 0.28, 0.2);
  const badge = mesh(new THREE.CircleGeometry(0.25, 32), new THREE.MeshBasicMaterial({ map: badgeTexture() }), bag, 0, 0.2, -0.34);
  badge.rotation.y = Math.PI;

  // Limbs hang from pivots at the shoulders and hips.
  const limbAt = (x, y, length, radius, material) => {
    const pivot = new THREE.Group();
    pivot.position.set(x, y, 0);
    fig.add(pivot);
    mesh(new THREE.CapsuleGeometry(radius, length, 6, 14), material, pivot, 0, -length / 2 - radius / 2, 0);
    return pivot;
  };
  const armL = limbAt(-0.92, 0.02, 0.44, 0.14, limb);
  const armR = limbAt(0.92, 0.02, 0.44, 0.14, limb);
  const legL = limbAt(-0.4, -0.8, 0.16, 0.14, limb);
  const legR = limbAt(0.4, -0.8, 0.16, 0.14, limb);
  for (const leg of [legL, legR]) mesh(small, ink, leg, 0, -0.42, 0.1).scale.set(0.24, 0.14, 0.34);

  // Open book, held for reading.
  const book = new THREE.Group();
  book.position.set(0, -0.42, 1.2);
  fig.add(book);
  for (const side of [-1, 1]) {
    const leaf = new THREE.Group();
    leaf.rotation.y = side * 0.35;
    book.add(leaf);
    mesh(new THREE.BoxGeometry(0.56, 0.7, 0.03), new THREE.MeshStandardMaterial({ color: 0xd32f2f }), leaf, side * 0.28, 0, -0.03);
    mesh(new THREE.BoxGeometry(0.5, 0.64, 0.04), white, leaf, side * 0.27, 0, 0);
  }

  // Steam for when he is angry.
  const puffs = [0, 1, 2, 3, 4, 5].map(i => {
    const puff = mesh(small, new THREE.MeshStandardMaterial({ color: 0xffffff, transparent: true, roughness: 1 }), fig);
    puff.userData.side = i % 2 ? 1 : -1;
    puff.userData.delay = i / 6;
    return puff;
  });

  return { yaw, tumble, fig, eyes, pupils, smile, frown, open, brows, book, armL, armR, legL, legR, puffs, skin, limb };
}

export function mount(root, read) {
  const hit = root.querySelector('.abj-hit');
  const canvas = document.createElement('canvas');
  canvas.className = 'abj-canvas';
  canvas.setAttribute('aria-hidden', 'true');
  const ground = document.createElement('div');
  ground.className = 'abj-ground';

  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: 'low-power' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  hit.append(ground, canvas);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(22, 1, 0.1, 40);
  camera.position.set(0, 1.5, 12.8);
  camera.lookAt(0, 0, 0);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8a6a6a, 2.1));
  const sun = new THREE.DirectionalLight(0xffffff, 2.4);
  sun.position.set(-3, 5, 6);
  scene.add(sun);

  const a = build();
  scene.add(a.yaw);

  function resize() {
    const size = hit.offsetWidth * 1.7;
    if (size) renderer.setSize(size, size, false);
  }
  resize();
  window.addEventListener('resize', resize);

  let state = '', since = 0, last = performance.now(), running = true;
  let yaw = 0, heat = 0, lift = 0, squashX = 1, squashY = 1, blinkAt = 2, blinkEnd = 0;
  const clock = { t: 0 };

  function pose(dt) {
    const now = read();
    const t = clock.t;
    if (root.dataset.state !== state) {
      state = root.dataset.state;
      since = 0;
      if (state === 'spin') yaw %= Math.PI * 2;
    }
    since += dt;

    // Which way he faces. Walking shows his side, spinning shows everything.
    let turn = Math.sin(t * 0.6) * 0.16;
    if (state === 'walk') turn = now.dir * 1.05;
    else if (state === 'leap') turn = now.dir * 0.75;
    else if (state === 'flip' || state === 'read' || state === 'angry' || state === 'sleep') turn = 0;
    if (state === 'spin') yaw = Math.PI * 2 * ease(clamp01(since / 2.6));
    else {
      if (yaw > Math.PI) yaw -= Math.PI * 2;
      yaw = damp(yaw, turn, 7, dt);
    }
    a.yaw.rotation.y = yaw;

    // Somersault: a real turn in depth, around his own middle.
    let flipAngle = 0, height = 0;
    if (state === 'leap') flipAngle = now.rot * Math.PI / 180;
    if (state === 'flip') {
      const p = clamp01(since / 0.9);
      flipAngle = Math.PI * 2 * ease(p);
      height = 84 * Math.sin(Math.PI * p);
    }
    if (state === 'jump') height = 62 * Math.abs(Math.sin(Math.PI * since / 0.75));
    a.tumble.rotation.x = flipAngle;

    // Limb targets.
    let armZ = 0.22, armX = 0, armXR = 0, armRZ = 0.22, legSwing = 0, bob = 0, roll = 0, pitch = 0;
    let lookX = now.px * 0.012, lookY = -now.py * 0.012;
    if (state === 'walk') {
      const s = Math.sin(t * 13);
      legSwing = s * 0.75;
      armX = s * 0.7;
      armXR = -s * 0.7;
      bob = Math.abs(Math.cos(t * 13)) * 0.06;
    } else if (state === 'jump' || state === 'leap' || state === 'flip') {
      armZ = armRZ = 1.5;
      legSwing = 0.25;
    } else if (state === 'wave') {
      armRZ = 2.5 + Math.sin(t * 12) * 0.32;
    } else if (state === 'dance') {
      armZ = 2.1 + Math.sin(t * 9) * 0.4;
      armRZ = 2.1 - Math.sin(t * 9) * 0.4;
      roll = Math.sin(t * 6) * 0.16;
      bob = Math.abs(Math.sin(t * 6)) * 0.14;
    } else if (state === 'read') {
      armX = armXR = -1.25;
      armZ = armRZ = -0.05;
      lookY = -0.05;
      pitch = 0.1;
    } else if (state === 'dizzy') {
      roll = Math.sin(t * 7) * 0.12;
      lookX = Math.cos(t * 13) * 0.035;
      lookY = Math.sin(t * 13) * 0.035;
    } else if (state === 'angry') {
      armZ = armRZ = 0.95 + Math.sin(t * 22) * 0.16;
      legSwing = Math.sin(t * 20) * 0.32;
      roll = Math.sin(t * 34) * 0.05;
      bob = Math.abs(Math.sin(t * 20)) * 0.05;
      lookX = lookY = 0;
    } else if (state === 'calm') {
      armZ = armRZ = 0.08;
      pitch = 0.09;
    } else if (state === 'sleep') {
      armZ = armRZ = 0.05;
      pitch = 0.08;
      roll = 0.07;
    }

    a.armL.rotation.z = damp(a.armL.rotation.z, -armZ, 16, dt);
    a.armR.rotation.z = damp(a.armR.rotation.z, armRZ, 16, dt);
    a.armL.rotation.x = damp(a.armL.rotation.x, armX, 18, dt);
    a.armR.rotation.x = damp(a.armR.rotation.x, armXR, 18, dt);
    a.legL.rotation.x = damp(a.legL.rotation.x, legSwing, 22, dt);
    a.legR.rotation.x = damp(a.legR.rotation.x, -legSwing, 22, dt);
    a.fig.rotation.z = damp(a.fig.rotation.z, roll, 18, dt);
    a.fig.rotation.x = damp(a.fig.rotation.x, pitch, 8, dt);
    a.pupils.position.x = damp(a.pupils.position.x, lookX, 14, dt);
    a.pupils.position.y = damp(a.pupils.position.y, lookY, 14, dt);

    // Squash on take-off and landing; a breath while standing.
    let sx = 1, sy = 1;
    if (state === 'land') { sx = 1.14; sy = 0.84; }
    else if (state === 'idle' || state === 'read' || state === 'calm') sy = 1 + Math.sin(t * 2.2) * 0.012;
    else if (state === 'sleep') sy = 1 + Math.sin(t * 1.3) * 0.02;
    squashX = damp(squashX, sx, 18, dt);
    squashY = damp(squashY, sy, 18, dt);
    a.fig.scale.set(squashX, squashY, squashX);
    a.fig.position.y = bob;

    if (t > blinkAt) {
      blinkEnd = t + 0.11;
      blinkAt = t + 2.5 + Math.random() * 3;
    }
    a.eyes.scale.y = state === 'sleep' || (t < blinkEnd && state !== 'angry') ? 0.1 : 1;

    // Temper: flashes yellow and red, then cools back to his own colour.
    heat = damp(heat, state === 'angry' ? 1 : 0, state === 'angry' ? 7 : 2.4, dt);
    const flash = 0.5 + 0.5 * Math.sin(t * 15);
    a.skin.color.copy(SKIN).lerp(HOT, heat * flash);
    a.limb.color.copy(LIMB).lerp(HOT, heat * flash * 0.75);
    a.skin.emissive.copy(HOT).multiplyScalar(heat * flash * 0.22);
    const cross = state === 'angry';
    const merry = state === 'jump' || state === 'wave' || state === 'dance' || state === 'flip' || state === 'leap';
    a.smile.visible = !cross && !merry;
    a.frown.visible = cross;
    a.open.visible = merry;
    a.brows.forEach(b => { b.visible = heat > 0.2; });
    a.book.visible = state === 'read';
    a.puffs.forEach((puff, i) => {
      const p = (t * 0.9 + puff.userData.delay) % 1;
      puff.visible = heat > 0.35;
      puff.position.set(puff.userData.side * (0.62 + p * 0.42), 0.9 + p * 0.75, 0.12 * (i % 3 - 1));
      puff.scale.setScalar(0.13 + p * 0.2);
      puff.material.opacity = 0.9 * (1 - p * 0.75);
    });

    // Height is the page moving him: a canvas this small can't hold a jump.
    const scale = hit.offsetWidth / FIG_PX;
    lift = height * scale;
    canvas.style.transform = 'translateY(' + (-lift).toFixed(1) + 'px)';
    ground.style.transform = 'translateX(-50%) scale(' + (1 - clamp01(lift / 120) * 0.5).toFixed(2) + ')';
    ground.style.opacity = state === 'leap' ? 0 : (1 - clamp01(lift / 120) * 0.6).toFixed(2);
  }

  function frame(now) {
    if (!running) return;
    requestAnimationFrame(frame);
    if (root.hidden) { last = now; return; }
    // Asleep he barely moves, so a few frames a second is enough and saves battery.
    if (root.dataset.state === 'sleep' && now - last < 120) return;
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    clock.t += dt;
    pose(dt);
    renderer.render(scene, camera);
  }

  canvas.addEventListener('webglcontextlost', e => {
    e.preventDefault();
    running = false;
    canvas.remove();
    ground.remove();
    root.classList.remove('abj-3d');
  });

  root.classList.add('abj-3d');
  requestAnimationFrame(frame);
}
