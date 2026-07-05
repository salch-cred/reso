// header scroll state
const hdr=document.getElementById('hdr');
const onScroll=()=>{hdr.classList.toggle('scrolled',window.scrollY>12)};
onScroll();window.addEventListener('scroll',onScroll,{passive:true});

// reveal on scroll (60fps: opacity+transform only)
const io=new IntersectionObserver((es)=>{es.forEach(e=>{if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{threshold:.14,rootMargin:'0px 0px -8% 0px'});
document.querySelectorAll('.reveal').forEach(el=>io.observe(el));

// marquee build (duplicate for seamless loop)
const logos=[['Stellar','M12 3v18M5 8l7-5 7 5'],['Soroban','M8 4l-4 8 4 8M16 4l4 8-4 8'],['Paillier FHE','M5 11h14v9H5zM8 11V8a4 4 0 0 1 8 0v3'],['Nova IVC','M12 3l8 5v8l-8 5-8-5V8z'],['Shamir SSS','M12 3v18M5 8l7 4 7-4'],['Merkle','M12 3v6M6 21l6-8 6 8'],['SEP-8','M4 6h16v12H4zM4 9h16'],['Groth16','M12 2 4 6v6c0 5 3.5 7.5 8 10 4.5-2.5 8-5 8-10V6l-8-4Z']];
const mk=(n,p)=>`<div class="logo-item"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${p}"/></svg>${n}</div>`;
const html=logos.map(l=>mk(l[0],l[1])).join('');
document.getElementById('mq').innerHTML=html+html;

// console proof sequence
const rows=[...document.querySelectorAll('.proof-row')];
const bar=document.getElementById('pbar');
function runProofs(){
  rows.forEach(r=>r.classList.remove('show'));
  if(bar)bar.style.transition='none',bar.style.width='0%';
  rows.forEach((r,i)=>setTimeout(()=>r.classList.add('show'),500+i*650));
  setTimeout(()=>{if(bar){bar.style.transition='width 1.6s cubic-bezier(.22,.61,.36,1)';bar.style.width='100%'}},700);
}
const cons=document.querySelector('.console');
if(cons){const co=new IntersectionObserver((es)=>{es.forEach(e=>{if(e.isIntersecting){runProofs();setInterval(runProofs,5200)}})},{threshold:.4});co.observe(cons);co.takeRecords();}

// count-up stats
const animateCount=(el)=>{const to=+el.dataset.to;const dur=1200;const t0=performance.now();
  const tick=(t)=>{const p=Math.min((t-t0)/dur,1);const e=1-Math.pow(1-p,3);el.textContent=Math.round(to*e);if(p<1)requestAnimationFrame(tick)};requestAnimationFrame(tick)};
const so=new IntersectionObserver((es)=>{es.forEach(e=>{if(e.isIntersecting){animateCount(e.target);so.unobserve(e.target)}})},{threshold:.6});
document.querySelectorAll('.count').forEach(el=>so.observe(el));

// mobile menu (simple)
document.querySelector('.nav-toggle').addEventListener('click',()=>{alert('Reso — mobile navigation')});
