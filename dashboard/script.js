// header scroll
const hdr = document.getElementById('hdr');
const onScroll = () => { hdr.classList.toggle('scrolled', window.scrollY > 12); };
onScroll(); window.addEventListener('scroll', onScroll, { passive: true });

// reveal on scroll
const io = new IntersectionObserver((es) => {
  es.forEach(e => { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
}, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
document.querySelectorAll('.reveal').forEach(el => io.observe(el));

// marquee logos
const logos = [
  ['Stellar', 'hgi-global'],
  ['Soroban', 'hgi-source-code'],
  ['Paillier FHE', 'hgi-lock-01'],
  ['Nova IVC', 'hgi-layers-01'],
  ['Shamir SSS', 'hgi-user-multiple-02'],
  ['Merkle Trees', 'hgi-git-fork'],
  ['SEP-8', 'hgi-checkmark-circle-01'],
  ['Groth16', 'hgi-shield-01'],
];
const mk = (name, icon) =>
  `<div class="logo-item"><i class="hgi-stroke ${icon}"></i>${name}</div>`;
const html = logos.map(l => mk(l[0], l[1])).join('');
const mq = document.getElementById('mq');
if (mq) mq.innerHTML = html + html;

// console proof animation
const rows = [...document.querySelectorAll('.proof-row')];
const bar = document.getElementById('pbar');
function runProofs() {
  rows.forEach(r => r.classList.remove('show'));
  if (bar) { bar.style.transition = 'none'; bar.style.width = '0%'; }
  rows.forEach((r, i) => setTimeout(() => r.classList.add('show'), 400 + i * 600));
  setTimeout(() => {
    if (bar) { bar.style.transition = 'width 1.8s cubic-bezier(.22,.61,.36,1)'; bar.style.width = '100%'; }
  }, 600);
}
const cons = document.querySelector('.console');
if (cons) {
  let interval;
  const co = new IntersectionObserver((es) => {
    es.forEach(e => {
      if (e.isIntersecting) { runProofs(); interval = setInterval(runProofs, 5000); }
      else { clearInterval(interval); }
    });
  }, { threshold: 0.3 });
  co.observe(cons);
}

// count-up stats
const animateCount = (el) => {
  const to = +el.dataset.to; const dur = 1100; const t0 = performance.now();
  const tick = (t) => {
    const p = Math.min((t - t0) / dur, 1);
    const e = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(to * e);
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
};
const so = new IntersectionObserver((es) => {
  es.forEach(e => { if (e.isIntersecting) { animateCount(e.target); so.unobserve(e.target); } });
}, { threshold: 0.6 });
document.querySelectorAll('.count').forEach(el => so.observe(el));

// mobile nav toggle
const toggle = document.querySelector('.nav-toggle');
const navLinks = document.querySelector('.nav-links');
if (toggle && navLinks) {
  toggle.addEventListener('click', () => {
    const open = navLinks.style.display === 'flex';
    navLinks.style.display = open ? '' : 'flex';
    navLinks.style.flexDirection = 'column';
    navLinks.style.position = 'absolute';
    navLinks.style.top = '68px';
    navLinks.style.left = '12px';
    navLinks.style.right = '12px';
    navLinks.style.background = '#fff';
    navLinks.style.border = '1px solid #E4E4E7';
    navLinks.style.borderRadius = '12px';
    navLinks.style.padding = '8px';
    navLinks.style.boxShadow = '0 8px 24px rgba(0,0,0,.1)';
    navLinks.style.zIndex = '300';
  });
}

// scroll progress bar
const progressBar = document.createElement('div');
progressBar.className = 'scroll-progress';
document.body.appendChild(progressBar);
const updateProgress = () => {
  const h = document.documentElement;
  const scrolled = (h.scrollTop) / (h.scrollHeight - h.clientHeight || 1) * 100;
  progressBar.style.width = scrolled + '%';
};
updateProgress();
window.addEventListener('scroll', updateProgress, { passive: true });

// cursor spotlight glow
const spotlight = document.createElement('div');
spotlight.className = 'spotlight';
document.body.appendChild(spotlight);
window.addEventListener('mousemove', (e) => {
  spotlight.style.opacity = '1';
  spotlight.style.left = e.clientX + 'px';
  spotlight.style.top = e.clientY + 'px';
}, { passive: true });
window.addEventListener('mouseleave', () => { spotlight.style.opacity = '0'; });

// magnetic buttons + 3D tilt cards (desktop pointer only, respects reduced motion)
(function () {
  const canHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (!canHover || reduced) return;

  document.querySelectorAll('.btn-lg').forEach((btn) => {
    let raf = null;
    let lastEvent = null;
    const apply = () => {
      if (!lastEvent) return;
      const r = btn.getBoundingClientRect();
      const x = lastEvent.clientX - (r.left + r.width / 2);
      const y = lastEvent.clientY - (r.top + r.height / 2);
      btn.style.transform = `translate(${(x * 0.18).toFixed(2)}px, ${(y * 0.35).toFixed(2)}px)`;
      raf = null;
    };
    btn.addEventListener('pointermove', (e) => {
      lastEvent = e;
      if (raf === null) raf = requestAnimationFrame(apply);
    });
    btn.addEventListener('pointerleave', () => { btn.style.transform = ''; });
  });

  const tiltEls = document.querySelectorAll('.card, .feat, .step, .uc, .integ, .quote, .gstat');
  tiltEls.forEach((el) => {
    let raf = null;
    let lastEvent = null;
    const apply = () => {
      if (!lastEvent) return;
      const r = el.getBoundingClientRect();
      const px = (lastEvent.clientX - r.left) / r.width - 0.5;
      const py = (lastEvent.clientY - r.top) / r.height - 0.5;
      el.style.transform = `perspective(700px) rotateX(${(-py * 7).toFixed(2)}deg) rotateY(${(px * 9).toFixed(2)}deg) translateY(-4px)`;
      raf = null;
    };
    el.addEventListener('pointerenter', () => { el.style.willChange = 'transform'; });
    el.addEventListener('pointermove', (e) => {
      lastEvent = e;
      if (raf === null) raf = requestAnimationFrame(apply);
    });
    el.addEventListener('pointerleave', () => {
      el.style.transform = '';
      el.style.willChange = 'auto';
    });
  });
})();
