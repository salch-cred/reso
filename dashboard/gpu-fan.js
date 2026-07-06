/* =====================================================
   RESO — Ambient GPU/Fan Background Sound & Ambient Sci-Fi Music
   Fully synthesized (no external audio files) low fan/turbine
   hum and drifting cosmic synth pads that play continuously in
   the background across pages, with a floating mute/unmute toggle.
   Preference is remembered in localStorage so it persists across
   the landing page and the console.
   ===================================================== */
(function(){
  var STORAGE_KEY='resoGpuSoundMuted';
  var ctx=null,master=null,started=false;
  var muted=localStorage.getItem(STORAGE_KEY)==='1';
  var musicTimer=null;
  var activeNodes=[];

  var ICON_ON='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="17" height="17"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14\"></path></svg>';
  var ICON_OFF='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="17" height="17"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15\"></line><line x1="17" y1="9" x2="23" y2="15\"></line></svg>';

  function buildNoiseBuffer(){
    var len=ctx.sampleRate*2;
    var buffer=ctx.createBuffer(1,len,ctx.sampleRate);
    var data=buffer.getChannelData(0);
    for(var i=0;i<len;i++)data[i]=Math.random()*2-1;
    return buffer;
  }

  // Drifting chords (frequencies in Hz)
  // Progression: Am9 -> Fmaj9 -> G6/9 -> Em9
  var CHORDS = [
    [110.00, 130.81, 164.81, 196.00, 246.94], // Am9
    [87.31, 130.81, 174.61, 218.08, 261.63],  // Fmaj9
    [98.00, 146.83, 196.00, 220.00, 293.66],  // G6/9
    [82.41, 123.47, 164.81, 196.00, 246.94]   // Em9
  ];
  var currentChordIdx = 0;

  function playAmbientPad() {
    if (!started || muted || !ctx) return;
    
    var now = ctx.currentTime;
    var chord = CHORDS[currentChordIdx];
    var duration = 9.0; // 9 seconds per chord
    var fadeTime = 3.0; // 3 seconds fade-in / fade-out
    
    // Create a local gain node for this chord
    var chordGain = ctx.createGain();
    chordGain.gain.setValueAtTime(0, now);
    chordGain.gain.linearRampToValueAtTime(0.06, now + fadeTime);
    chordGain.gain.setValueAtTime(0.06, now + duration - fadeTime);
    chordGain.gain.linearRampToValueAtTime(0, now + duration);
    
    var biquad = ctx.createBiquadFilter();
    biquad.type = 'lowpass';
    biquad.frequency.setValueAtTime(320, now);
    biquad.frequency.exponentialRampToValueAtTime(650, now + duration/2);
    biquad.frequency.exponentialRampToValueAtTime(320, now + duration);
    biquad.Q.value = 1.8;
    
    chordGain.connect(biquad);
    biquad.connect(master);
    
    var oscillators = [];
    chord.forEach(function(freq) {
      var osc = ctx.createOscillator();
      // Mix sine & soft triangle for a warm analog feel
      osc.type = Math.random() > 0.5 ? 'triangle' : 'sine';
      // Slight detune for chorus/drifting effect
      osc.frequency.setValueAtTime(freq + (Math.random() * 0.4 - 0.2), now);
      osc.connect(chordGain);
      osc.start(now);
      osc.stop(now + duration + 0.1);
      oscillators.push(osc);
    });

    // Schedule cleanup
    setTimeout(function() {
      oscillators.forEach(function(osc) {
        try { osc.disconnect(); } catch(e) {}
      });
      try { chordGain.disconnect(); biquad.disconnect(); } catch(e) {}
    }, (duration + 1) * 1000);

    // Progress to next chord
    currentChordIdx = (currentChordIdx + 1) % CHORDS.length;
    
    // Queue next chord 2 seconds before this one finishes to blend seamlessly
    musicTimer = setTimeout(playAmbientPad, (duration - fadeTime) * 1000);
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
    var rumbleGain=ctx.createGain();rumbleGain.gain.value=0.35;

    // Subtle blade-pass amplitude flutter
    var bladeLfo=ctx.createOscillator();
    bladeLfo.type='sine';bladeLfo.frequency.value=5.4;
    var bladeDepth=ctx.createGain();bladeDepth.gain.value=0.12;
    var bladeTarget=ctx.createGain();bladeTarget.gain.value=0.88;
    bladeLfo.connect(bladeDepth);bladeDepth.connect(bladeTarget.gain);

    noise.connect(bandpass);bandpass.connect(lowpass);lowpass.connect(bladeTarget);bladeTarget.connect(master);
    rumble.connect(rumbleGain);rumbleGain.connect(master);

    noise.start();rumble.start();bladeLfo.start();

    activeNodes = [noise, rumble, bladeLfo];

    if(!muted){
      var now=ctx.currentTime;
      master.gain.setValueAtTime(0,now);
      master.gain.linearRampToValueAtTime(0.06,now+1.2);
      playAmbientPad();
    }
  }

  function setMuted(m){
    muted=m;
    localStorage.setItem(STORAGE_KEY,m?'1':'0');
    if(master&&ctx){
      var now=ctx.currentTime;
      master.gain.cancelScheduledValues(now);
      master.gain.setValueAtTime(master.gain.value,now);
      master.gain.linearRampToValueAtTime(m?0:0.06,now+.4);
      
      clearTimeout(musicTimer);
      if(!m) {
        playAmbientPad();
      }
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
