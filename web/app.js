// ====== Dynamic API base + prefix detection ======
const ORIGIN = location.origin;
let API_PREFIX = '/api'; // default; we'll verify and auto-fix
const statusEl = document.getElementById('status');
const apiEl = document.getElementById('api');

// Small fetch helper with timeout + JSON fallback
async function fetchJSON(url, opts = {}, timeoutMs = 5000) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { ...opts, signal: ctrl.signal });
    let body;
    try { body = await r.clone().json(); } catch { body = await r.text(); }
    return { ok: r.ok, status: r.status, body };
  } finally {
    clearTimeout(to);
  }
}

// Try /api/healthz then /healthz; remember which works
async function detectApiPrefix() {
  for (const prefix of ['/api', '']) {
    const url = `${ORIGIN}${prefix}/healthz`;
    try {
      const { ok, body } = await fetchJSON(url, {}, 3000);
      if (ok && (body?.ok === true || body === '{"ok": true}' || body?.includes?.('"ok":'))) {
        return prefix;
      }
    } catch { /* try next */ }
  }
  return '/api'; // fallback
}

(async () => {
  API_PREFIX = await detectApiPrefix();
  apiEl.textContent = API_PREFIX || '/';
  try {
    const { ok } = await fetchJSON(`${ORIGIN}${API_PREFIX}/healthz`, {}, 3000);
    statusEl.textContent = ok ? 'Online' : 'Degraded';
    statusEl.className = ok ? 'ok' : 'warn';
  } catch {
    statusEl.textContent = 'Offline';
    statusEl.className = 'bad';
  }
})();
// ====== UI refs ======
const micState = document.getElementById('micState');
const vadState = document.getElementById('vadState');
const startBtn  = document.getElementById('start');
const stopBtn   = document.getElementById('stop');
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

// ====== Toast / Log ======
let toastTimer;
function toast(msg, cls=''){ clearTimeout(toastTimer); toastEl.textContent = msg; toastEl.className = `toast show ${cls}`; toastTimer=setTimeout(()=>toastEl.className='toast',2400); }
function log(...a){ console.log(...a); logEl.textContent += a.map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' ')+'\n'; logEl.scrollTop = logEl.scrollHeight; }
// ====== VAD params ======
let VAD_THRESHOLD = 0.02;     // base RMS
const VAD_HANGOVER_MS = 350;  // silence to end speech
let vadSpeaking = false;
let vadSilenceSince = 0;
let noiseFloor = 0.01;        // adaptive noise floor

// ====== Audio state ======
let ctx, analyser, source, rafId;
let stream, recorder, chunks = [], recording = false;
let recStartTime = 0;

// ====== TTS control ======
let ttsAbort;        // AbortController for in-flight TTS fetch
let ttsBlobURL = ''; // for cleanup
function drawScope() {
  const c = scope.getContext('2d');
  const w = scope.width = scope.clientWidth;
  const h = scope.height = scope.clientHeight;

  const data = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(data);

  // energy 0..1
  let sum = 0, peak = 0;
  for (let i=0;i<data.length;i++){
    const v = (data[i]-128)/128;
    sum += v*v;
    if (Math.abs(v) > peak) peak = Math.abs(v);
  }
  const energy = Math.sqrt(sum/data.length);
  level.style.width = `${Math.min(100, Math.round(energy*100))}%`;

  // draw
  c.clearRect(0,0,w,h);
  c.lineWidth = 2; c.strokeStyle = 'rgba(76,201,240,.9)'; c.beginPath();
  const slice = w / data.length;
  for (let i=0;i<data.length;i++){
    const x = i * slice, y = (data[i]/255)*h;
    if (i===0) c.moveTo(x,y); else c.lineTo(x,y);
  }
  c.stroke();

  // adaptive floor (slow follow)
  noiseFloor = 0.98*noiseFloor + 0.02*energy;
  const dynThresh = Math.max(VAD_THRESHOLD, noiseFloor * 2.25);

  // VAD
  const now = performance.now();
  if (energy >= dynThresh) {
    if (!vadSpeaking) onSpeechStart();
    vadSpeaking = true;
    vadSilenceSince = 0;
  } else if (vadSpeaking) {
    if (!vadSilenceSince) vadSilenceSince = now;
    if (now - vadSilenceSince > VAD_HANGOVER_MS) {
      onSpeechEnd();
      vadSpeaking = false;
      vadSilenceSince = 0;
    }
  }

  rafId = requestAnimationFrame(drawScope);
}
async function onSpeechStart(){
  vadState.textContent = 'speaking';
  vadState.className = 'ok';
  micState.textContent = recording ? 'recording' : 'armed';

  // HARD-STOP any TTS instantly (local + server)
  stopTTSLocal();
  try { await fetch(`${ORIGIN}${API_PREFIX}/tts/stop`, { method:'POST' }); } catch {}

  // Start recorder if not already recording
  if (!recording) {
    chunks = [];
    const mimeType = chooseMime();
    try {
      recorder = new MediaRecorder(stream, { mimeType });
    } catch (e) {
      log('MediaRecorder init failed, retrying with default:', e?.message || e);
      recorder = new MediaRecorder(stream);
    }
    recorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    recorder.onstop = () => { if (chunks.length) uploadChunk(recorder.mimeType || mimeType); };
    recorder.start(100);
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
function chooseMime() {
  // Progressive MIME fallback for widest browser support
  const prefs = [
    mimeSel?.value,
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',           // iOS Safari
    'audio/mpeg'           // mp3 (last resort; often not supported for MediaRecorder)
  ].filter(Boolean);

  for (const m of prefs) {
    if (MediaRecorder.isTypeSupported?.(m)) return m;
  }
  return ''; // let browser pick
}

async function uploadChunk(mimeType){
  try{
    const blob = new Blob(chunks, { type: mimeType || 'audio/webm' });
    chunks = []; // free memory early
    if (!blob.size) return;
    const ext = (mimeType?.split?.('/')[1] || 'webm').split(';')[0] || 'webm';

    const fd = new FormData();
    fd.append('file', blob, `input.${ext}`);

    const r = await fetch(`${ORIGIN}${API_PREFIX}/transcribe`, { method:'POST', body: fd });
    if (!r.ok) {
      let d = await r.text(); try{ d = JSON.stringify(JSON.parse(d)) }catch{}
      throw new Error(`${r.status} ${r.statusText} ${d}`);
    }
    const data = await r.json();
    const text = data.text || '';
    transcriptEl.textContent = text;

    // OPTIONAL: send to your intent router
    // await fetch(`${ORIGIN}${API_PREFIX}/determine_intent`, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({message:text})});
  }catch(e){
    log('Transcribe failed:', e?.message || e);
    toast('Transcribe failed', 'bad');
  }
}
// ====== Mic start / stop ======
async function start(){
  try{
    stream = await navigator.mediaDevices.getUserMedia({ audio:{ noiseSuppression:true, echoCancellation:true } });
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    source = ctx.createMediaStreamSource(stream);
    analyser = ctx.createAnalyser();
    analyser.fftSize = 2048;
    source.connect(analyser);

    drawScope();
    startBtn.disabled = true; stopBtn.disabled = false;
    micState.textContent = 'armed';
    vadState.textContent = 'ready'; vadState.className = 'muted';
    toast('Mic ready. Start speaking…','ok');
  }catch(e){
    toast('Microphone blocked', 'bad');
    log('getUserMedia error:', e?.message || e);
  }
}

function stop(){
  try{
    cancelAnimationFrame(rafId);
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    if (stream) stream.getTracks().forEach(t=>t.stop());
    if (ctx && ctx.state !== 'closed') ctx.close();
  }catch{}
  startBtn.disabled = false; stopBtn.disabled = true;
  micState.textContent = 'idle';
  vadState.textContent = 'ready'; vadState.className = 'muted';
}
// ====== TTS: speak, but abort on user speech ======
async function speak(){
  const text = ttsTextEl.value.trim();
  const voice = voiceEl.value || 'alloy';
  if (!text) return toast('Enter text', 'warn');

  stopTTSLocal(); // clear any previous
  ttsAbort = new AbortController();

  try{
    const resp = await fetch(`${ORIGIN}${API_PREFIX}/tts`, {
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
    try { await player.play(); } catch {} // autoplay policies
    toast('Speaking…','ok');
  }catch(e){
    if (e.name === 'AbortError') return; // expected on VAD start
    log('TTS error:', e?.message || e);
    toast('TTS failed','bad');
  }
}

function stopTTSLocal(){
  try{ player.pause(); }catch{}
  if (ttsAbort) { try { ttsAbort.abort(); } catch {} ttsAbort = undefined; }
  if (ttsBlobURL) { URL.revokeObjectURL(ttsBlobURL); ttsBlobURL = ''; }
}

async function stopTTS(){
  stopTTSLocal();
  try { await fetch(`${ORIGIN}${API_PREFIX}/tts/stop`, { method:'POST' }); } catch {}
  toast('TTS stopped','warn');
}

// ====== UI events ======
document.getElementById('start').addEventListener('click', start);
document.getElementById('stop').addEventListener('click', stop);
document.getElementById('speak').addEventListener('click', speak);
document.getElementById('stopTTS').addEventListener('click', stopTTS);

// keep canvas live for ResizeObserver
scope.addEventListener('click', ()=>{});
new ResizeObserver(()=>{}).observe(scope);
