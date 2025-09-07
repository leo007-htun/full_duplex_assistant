const API_BASE = location.origin;

// UI
const statusEl = document.getElementById('status');
const apiEl = document.getElementById('api');
const micState = document.getElementById('micState');
const vadState = document.getElementById('vadState');
const startBtn = document.getElementById('start');
const stopBtn  = document.getElementById('stop');
const transcriptEl = document.getElementById('transcript');
const ttsTextEl = document.getElementById('ttsText');
const voiceEl = document.getElementById('voice');
const speakBtn = document.getElementById('speak');
const stopTTSBtn = document.getElementById('stopTTS');
const player = document.getElementById('player');
const logEl = document.getElementById('log');
const scope = document.getElementById('scope');
const level = document.getElementById('level');
const mimeSel = document.getElementById('mime');
const toastEl = document.getElementById('toast');

apiEl.textContent = '/api';

// toast
let toastTimer;
function toast(msg, cls=''){ clearTimeout(toastTimer); toastEl.textContent = msg; toastEl.className = `toast show ${cls}`; toastTimer = setTimeout(()=>toastEl.className='toast', 2400); }
// log
function log(...a){ console.log(...a); logEl.textContent += a.map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' ')+'\n'; logEl.scrollTop = logEl.scrollHeight; }

// health
(async () => {
  try { const r = await fetch(`${API_BASE}/api/healthz`); const j = await r.json(); statusEl.textContent = j?.ok?'Online':'Degraded'; statusEl.className = j?.ok?'ok':'warn'; }
  catch { statusEl.textContent = 'Offline'; statusEl.className = 'bad'; }
})();

// ======== VAD params ========
const VAD_THRESHOLD = 0.02;     // RMS threshold (~ energy)
const VAD_HANGOVER_MS = 350;    // wait this long of silence before end-of-speech
const FRAME_MS = 20;            // ~20ms analysis
let vadSpeaking = false;
let vadSilenceSince = 0;

// audio / analyser
let ctx, analyser, source, rafId;
let stream, recorder, chunks = [], recording = false;
let recStartTime = 0;

// TTS control
let ttsAbort;        // AbortController for in-flight TTS fetch
let ttsBlobURL = ''; // for cleanup

function rms(samples) {
  let sum = 0; for (let i=0;i<samples.length;i++){ const s = samples[i]/32768; sum += s*s; }
  return Math.sqrt(sum / samples.length);
}

function drawScope() {
  const c = scope.getContext('2d');
  const w = scope.width = scope.clientWidth;
  const h = scope.height = scope.clientHeight;

  const data = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(data);

  // compute level from 8-bit PCM -> convert to 16-bit-like range for our rms()
  let peak = 0, sum = 0;
  for (let i=0;i<data.length;i++){
    const v = (data[i]-128)/128;
    sum += v*v;
    peak = Math.max(peak, Math.abs(v));
  }
  const energy = Math.sqrt(sum/data.length);     // 0..1
  level.style.width = `${Math.min(100, Math.round(energy*100))}%`;

  c.clearRect(0,0,w,h);
  c.lineWidth = 2; c.strokeStyle = 'rgba(76,201,240,.9)'; c.beginPath();
  const slice = w / data.length;
  for (let i=0;i<data.length;i++){
    const x = i * slice; const y = (data[i]/255)*h;
    if (i===0) c.moveTo(x,y); else c.lineTo(x,y);
  }
  c.stroke();

  // VAD decision
  const now = performance.now();
  if (energy >= VAD_THRESHOLD) {
    // user speaking (transition if needed)
    if (!vadSpeaking) onSpeechStart();
    vadSpeaking = true;
    vadSilenceSince = 0;
  } else {
    // silence
    if (vadSpeaking) {
      if (!vadSilenceSince) vadSilenceSince = now;
      if (now - vadSilenceSince > VAD_HANGOVER_MS) {
        onSpeechEnd();
        vadSpeaking = false;
        vadSilenceSince = 0;
      }
    }
  }

  rafId = requestAnimationFrame(drawScope);
}

async function onSpeechStart(){
  vadState.textContent = 'speaking';
  vadState.className = 'ok';
  micState.textContent = recording ? 'recording' : 'armed';

  // 💥 HARD-STOP any TTS instantly
  stopTTSLocal();
  try { await fetch(`${API_BASE}/api/tts/stop`, { method:'POST' }); } catch {}

  // if we are not already recording, start a MediaRecorder session
  if (!recording) {
    chunks = [];
    const mimeType = mimeSel.value;
    recorder = new MediaRecorder(stream, { mimeType });
    recorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    recorder.onstop = () => { if (chunks.length) uploadChunk(mimeType); };
    recorder.start(100); // gather small chunks
    recording = true;
    recStartTime = performance.now();
  }
}

function onSpeechEnd(){
  vadState.textContent = 'silence';
  vadState.className = 'muted';

  if (recording && recorder && recorder.state !== 'inactive') {
    recorder.stop();
    recording = false;
  }
}

async function uploadChunk(mimeType){
  try{
    const blob = new Blob(chunks, { type: mimeType });
    if (!blob.size) return;
    const fd = new FormData();
    fd.append('file', blob, `input.${mimeType.split('/')[1] || 'webm'}`);

    const r = await fetch(`${API_BASE}/api/transcribe`, { method:'POST', body: fd });
    if (!r.ok) {
      let d = await r.text(); try{ d = JSON.stringify(JSON.parse(d)) }catch{}
      throw new Error(`${r.status} ${r.statusText} ${d}`);
    }
    const data = await r.json();
    const text = data.text || '';
    transcriptEl.textContent = text;

    // OPTIONAL: route it to your intent pipeline
    // await fetch(`${API_BASE}/api/determine_intent`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({message:text})});

  }catch(e){
    log('Transcribe failed:', e?.message || e);
    toast('Transcribe failed', 'bad');
  }
}

// start / stop mic
async function start(){
  try{
    stream = await navigator.mediaDevices.getUserMedia({ audio:true });
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    source = ctx.createMediaStreamSource(stream);
    analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    drawScope();
    startBtn.disabled = true; stopBtn.disabled = false;
    micState.textContent = 'armed';
    toast('Mic ready. Start speaking…','ok');
  }catch(e){
    toast('Microphone blocked', 'bad');
  }
}

function stop(){
  try{
    cancelAnimationFrame(rafId);
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    if (stream) stream.getTracks().forEach(t=>t.stop());
    if (ctx) ctx.close();
  }catch{}
  startBtn.disabled = false; stopBtn.disabled = true;
  micState.textContent = 'idle';
  vadState.textContent = 'ready'; vadState.className = 'muted';
}

// TTS: speak, but abort on user speech
async function speak(){
  const text = ttsTextEl.value.trim();
  const voice = voiceEl.value || 'alloy';
  if (!text) return toast('Enter text', 'warn');

  stopTTSLocal(); // clear any previous
  ttsAbort = new AbortController();

  try{
    const resp = await fetch(`${API_BASE}/api/tts`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ text, voice }),
      signal: ttsAbort.signal
    });

    if (!resp.ok) {
      let d = await resp.text(); try{ d = JSON.stringify(JSON.parse(d)) }catch{}
      throw new Error(`${resp.status} ${resp.statusText} ${d}`);
    }

    const buf = await resp.arrayBuffer();
    if (!buf.byteLength) throw new Error('Empty audio');

    const blob = new Blob([buf], { type:'audio/mpeg' });
    ttsBlobURL = URL.createObjectURL(blob);

    player.pause();
    player.src = ttsBlobURL;
    player.load();
    try { await player.play(); } catch { /* autoplay */ }
    toast('Speaking…','ok');
  }catch(e){
    if (e.name === 'AbortError') {
      // expected on VAD start
      return;
    }
    log('TTS error:', e?.message || e);
    toast('TTS failed','bad');
  }
}

function stopTTSLocal(){
  // stop audio element & abort in-flight fetch
  try{ player.pause(); }catch{}
  if (ttsAbort) { try { ttsAbort.abort(); } catch {} ttsAbort = undefined; }
  if (ttsBlobURL) { URL.revokeObjectURL(ttsBlobURL); ttsBlobURL = ''; }
}

async function stopTTS(){
  stopTTSLocal();
  try { await fetch(`${API_BASE}/api/tts/stop`, { method:'POST' }); } catch {}
  toast('TTS stopped','warn');
}

// UI events
startBtn.addEventListener('click', start);
stopBtn.addEventListener('click', stop);
speakBtn.addEventListener('click', speak);
stopTTSBtn.addEventListener('click', stopTTS);

// When user clicks play on the audio and then starts speaking, we still hard-stop
scope.addEventListener('click', ()=>{}); // keeps canvas active for resizing
new ResizeObserver(()=>{}).observe(scope);
