/* =====================================================
   RESO — Ambient GPU/Fan Background Sound
   Fully synthesized (no external audio files) low fan/turbine
   hum that plays continuously in the background across pages,
   with a floating mute/unmute toggle. Preference is remembered
   in localStorage so it persists across the landing page and
   the console.
   ===================================================== */
(function(){
  var STORAGE_KEY='resoGpuSoundMuted';
  var ctx=null,master=null,started=false;
  var muted=localStorage.getItem(STORAGE_KEY)==='1';

  var ICON_ON='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="17" height="17"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg>';
  var ICON_OFF='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="17" height="17"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>';

  function buildNoiseBuffer(){
    var len=ctx.sampleRate*2;
    var buffer=ctx.createBuffer(1,len,ctx.sampleRate);
    var data=buffer.getChannelData(0);
    for(var i=0;i<len;i++)data[i]=Math.random()*2-1;
    return buffer;
  }

  function startEngine(){
    if(started)return;
    var Ctx=window.AudioContext||window.webkitAudioContext;
    if(!Ctx)return;
    ctx=new Ctx();
    started=true;

    master=ctx.createGain();
    master.gain.value=0;
    master.connect(ctx.destination);

    // Broadband filtered noise = the whoosh of spinning fan blades
    var noise=ctx.createBufferSource();
    noise.buffer=buildNoiseBuffer();
    noise.loop=true;

    var bandpass=ctx.createBiquadFilter();
    bandpass.type='bandpass';bandpass.frequency.value=950;bandpass.Q.value=0.55;

    var lowpass=ctx.createBiquadFilter();
    lowpass.type='lowpass';lowpass.frequency.value=2800;

    // Low-frequency motor/coil rumble
    var rumble=ctx.createOscillator();
    rumble.type='sine';rumble.frequency.value=52;
    var rumbleGain=ctx.createGain();rumbleGain.gain.value=0.3;

    // Subtle blade-pass amplitude flutter
    var bladeLfo=ctx.createOscillator();
    bladeLfo.type='sine';bladeLfo.frequency.value=5.4;
    var bladeDepth=ctx.createGain();bladeDepth.gain.value=0.12;
    var bladeTarget=ctx.createGain();bladeTarget.gain.value=0.88;
    bladeLfo.connect(bladeDepth);bladeDepth.connect(bladeTarget.gain);

    noise.connect(bandpass);bandpass.connect(lowpass);lowpass.connect(bladeTarget);bladeTarget.connect(master);
    rumble.connect(rumbleGain);rumbleGain.connect(master);

    noise.start();rumble.start();bladeLfo.start();

    if(!muted){
      var now=ctx.currentTime;
      master.gain.setValueAtTime(0,now);
      master.gain.linearRampToValueAtTime(0.05,now+1.2);
    }
  }

  function setMuted(m){
    muted=m;
    localStorage.setItem(STORAGE_KEY,m?'1':'0');
    if(master&&ctx){
      var now=ctx.currentTime;
      master.gain.cancelScheduledValues(now);
      master.gain.setValueAtTime(master.gain.value,now);
      master.gain.linearRampToValueAtTime(m?0:0.05,now+.4);
    }
    updateButton();
  }

  function updateButton(){
    var btn=document.getElementById('resoGpuSoundBtn');
    if(!btn)return;
    btn.innerHTML=muted?ICON_OFF:ICON_ON;
    var label=muted?'Unmute background sound':'Mute background sound';
    btn.setAttribute('aria-label',label);
    btn.title=label;
  }

  function injectButton(){
    if(document.getElementById('resoGpuSoundBtn'))return;
    var btn=document.createElement('button');
    btn.id='resoGpuSoundBtn';
    btn.type='button';
    btn.style.cssText='position:fixed;bottom:20px;left:20px;z-index:9999;width:40px;height:40px;border-radius:50%;border:1.5px solid rgba(14,165,233,.35);background:rgba(255,255,255,.88);backdrop-filter:blur(10px) saturate(1.4);-webkit-backdrop-filter:blur(10px) saturate(1.4);box-shadow:0 4px 16px rgba(14,165,233,.18);display:flex;align-items:center;justify-content:center;cursor:pointer;color:#0EA5E9;transition:transform .15s ease,box-shadow .15s ease;';
    btn.addEventListener('mouseenter',function(){btn.style.transform='translateY(-2px)';btn.style.boxShadow='0 6px 20px rgba(14,165,233,.28)';});
    btn.addEventListener('mouseleave',function(){btn.style.transform='none';btn.style.boxShadow='0 4px 16px rgba(14,165,233,.18)';});
    btn.addEventListener('click',function(e){
      e.stopPropagation();
      if(!started)startEngine();
      if(ctx&&ctx.state==='suspended')ctx.resume();
      setMuted(!muted);
    });
    document.body.appendChild(btn);
    updateButton();
  }

  function firstInteraction(){
    if(!muted)startEngine();
    if(ctx&&ctx.state==='suspended')ctx.resume();
  }

  document.addEventListener('DOMContentLoaded',function(){
    injectButton();
    window.addEventListener('pointerdown',firstInteraction,{once:true});
    window.addEventListener('keydown',firstInteraction,{once:true});
  });
})();
