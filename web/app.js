// ===== API origin & prefix detection =====
const ORIGIN = location.origin;
let API_PREFIX = '/api';
const statusEl = document.getElementById('status');
const apiEl    = document.getElementById('api');

async function fetchJSON(url, opts = {}, timeoutMs = 5000) {
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { ...opts, signal: ctrl.signal });
    let body;
    try { body = await r.clone().json(); } catch { body = await r.text(); }
    return { ok: r.ok, status: r.status, body };
  } finally { clearTimeout(to); }
}
async function detectApiPrefix() {
  for (const prefix of ['/api', '']) {
    try {
      const { ok, body } = await fetchJSON(`${ORIGIN}${prefix}/healthz`, {}, 2500);
      if (ok && (body?.ok === true || (typeof body === 'string' && body.includes('"ok"')))) return prefix;
    } catch {}
  }
  return '/api';
}
(async () => {
  API_PREFIX = await detectApiPrefix();
  apiEl.textContent = API_PREFIX || '/';
  try {
    const { ok } = await fetchJSON(`${ORIGIN}${API_PREFIX}/healthz`, {}, 2500);
    statusEl.textContent = ok ? 'Online' : 'Degraded';
    statusEl.className = ok ? 'ok' : 'warn';
  } catch { statusEl.textContent = 'Offline'; statusEl.className = 'bad'; }
})();

// ===== UI refs =====
const micState = document.getElementById('micState');
const vadState = document.getElementById('vadState');
const startBtn = document.getElementById('start');
const stopBtn  = document.getElementById('stop');
const transcriptEl = document.getElementById('transcript');
const ttsTextEl = document.getElementById('ttsText');
const voiceEl   = document.getElementById('voice');
const speakBtn  = document.getElementById('speak');
const stopTTSBtn= document.getElementById('stopTTS');
const player    = document.getElementById('player');
const logEl     = document.getElementById('log');
const scope     = document.getElementById('scope');
const level     = document.getElementById('level');
const mimeSel   = document.getElementById('mime');
const toastEl   = document.getElementById('toast');

// ===== Toast / Log =====
let toastTimer;
function toast(msg, cls=''){ clearTimeout(toastTimer); toastEl.textContent=msg; toastEl.className=`toast show ${cls}`; toastTimer=setTimeout(()=>toastEl.className='toast',2400); }
function log(...a){ console.log(...a); logEl.textContent += a.map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' ')+'\n'; logEl.scrollTop=logEl.scrollHeight; }

// ===== VAD params =====
let VAD_THRESHOLD = 0.02;
const VAD_HANGOVER_MS = 350;
let vadSpeaking = false;
let vadSilenceSince = 0;
let noiseFloor = 0.01;

// ===== Audio state =====
let ctx, analyser, source, rafId;
let stream, recorder, chunks = [], recording = false;
// Abort in-flight intent request if user speaks again
let intentAbort = null;

// Keep the last LLM reply so the Speak button can replay it
let lastLLMReply = '';


// ===== TTS control (hard barge-in) =====
let ttsAbort;
let ttsBlobURL = '';
let ttsPlaying = false; // track playback to avoid self-barge-in

player.addEventListener('playing', () => { ttsPlaying = true; });
player.addEventListener('pause',   () => { ttsPlaying = false; });
player.addEventListener('ended',   () => { ttsPlaying = false; });

function stopTTSLocal(){
  try{ player.pause(); }catch{}
  ttsPlaying = false;
  if (ttsAbort && !ttsAbort.signal.aborted) try { ttsAbort.abort(); } catch {}
  ttsAbort = undefined;
  if (ttsBlobURL) { URL.revokeObjectURL(ttsBlobURL); ttsBlobURL=''; }
}
async function stopTTS(){
  stopTTSLocal();
  try { await fetch(`${ORIGIN}${API_PREFIX}/tts/stop`, { method:'POST' }); } catch {}
  toast('TTS stopped','warn');
}

// ===== Draw + VAD =====
function drawScope() {
  const c = scope.getContext('2d');
  const w = scope.width = scope.clientWidth;
  const h = scope.height = scope.clientHeight;

  const data = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(data);

  // energy estimate
  let sum=0, peak=0;
  for (let i=0;i<data.length;i++){
    const v=(data[i]-128)/128; sum+=v*v; if (Math.abs(v)>peak) peak=Math.abs(v);
  }
  const energy = Math.sqrt(sum/data.length);
  level.style.width = Math.min(100, Math.round(energy*100)) + '%';

  // scope
  c.clearRect(0,0,w,h);
  c.lineWidth=2; c.strokeStyle='rgba(76,201,240,.9)'; c.beginPath();
  const slice = w / data.length;
  for (let i=0;i<data.length;i++){
    const x=i*slice, y=(data[i]/255)*h;
    if (i===0) c.moveTo(x,y); else c.lineTo(x,y);
  }
  c.stroke();

  // adaptive floor + VAD decision
  noiseFloor = 0.98*noiseFloor + 0.02*energy;
  const dynThresh = Math.max(VAD_THRESHOLD, noiseFloor*2.25);

  // Stronger barge-in rule while TTS plays to reduce echo triggers
  const requireFactor = ttsPlaying ? 2.4 : 1.0;
  const now = performance.now();

  if (energy >= dynThresh * requireFactor) {
    if (!vadSpeaking) onSpeechStart();
    vadSpeaking = true;
    vadSilenceSince = 0;
  } else if (vadSpeaking) {
    if (!vadSilenceSince) vadSilenceSince = now;
    if (now - vadSilenceSince > VAD_HANGOVER_MS) {
      onSpeechEnd();
      vadSpeaking = false; vadSilenceSince = 0;
    }
  }
  rafId = requestAnimationFrame(drawScope);
}

async function onSpeechStart(){
  vadState.textContent = 'speaking'; vadState.className='ok';
  // HARD barge-in: stop local/server TTS immediately
  stopTTSLocal();
  try { await fetch(`${ORIGIN}${API_PREFIX}/tts/stop`, { method:'POST' }); } catch {}
  if (intentAbort && !intentAbort.signal.aborted) {
    try { intentAbort.abort(); } catch {}
  }

  if (!recording) {
    chunks = [];
    const mimeType = chooseMime();
    try { recorder = new MediaRecorder(stream, { mimeType }); }
    catch { recorder = new MediaRecorder(stream); }
    recorder.ondataavailable = e => { if (e.data && e.data.size) chunks.push(e.data); };
    recorder.onstop = () => {
      try {
        if (!chunks.length) {
          log('[onstop] No chunks collected — skipping upload.');
          return;
        }
        const mt = recorder.mimeType || mimeType || 'audio/webm';
        uploadChunk(mt).catch(e => {
          log('[onstop->uploadChunk] error:', e?.stack || e?.message || e);
          toast('Upload failed', 'bad');
        });
      } catch (e) {
        log('[onstop] handler error:', e?.stack || e?.message || e);
      }
    };

    recorder.start(150); // ~150ms chunks
    recording = true;
    micState.textContent = 'recording';
  }
}

function onSpeechEnd(){
  vadState.textContent = 'silence'; vadState.className='muted';
  if (recording && recorder && recorder.state !== 'inactive') {
    recorder.stop();
    recording = false;
    micState.textContent = 'armed';
  }
}

function chooseMime() {
  const prefs = [
    mimeSel?.value,
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/ogg',
    'audio/mp4',
    'audio/mpeg'
  ].filter(Boolean);
  for (const m of prefs) { if (MediaRecorder.isTypeSupported?.(m)) return m; }
  return ''; // let browser decide
}

// ===== Upload, then LLM, then TTS back =====
async function uploadChunk(mimeType){
  try{
    const blob = new Blob(chunks, { type: mimeType || 'audio/webm' });
    console.log('Uploading blob:', blob.size, 'bytes, type:', mimeType); 
    chunks = [];
    if (!blob.size) return;

    const ext = (mimeType?.split?.('/')[1] || 'webm').split(';')[0] || 'webm';
    const fd = new FormData();
    fd.append('file', blob, `input.${ext}`);

    // --- STT ---
    console.log('Sending STT request...');
    const sttResp = await fetch(`${ORIGIN}${API_PREFIX}/transcribe`, { 
      method: 'POST', 
      body: fd,
      signal: intentAbort?.signal // Attach abort signal here too
    });
    
    console.log('STT Response status:', sttResp.status);
    
    if (!sttResp.ok) {
      const errorText = await sttResp.text();
      console.error('[STT HTTP Error]', sttResp.status, errorText);
      throw new Error(`STT failed: ${sttResp.status} ${errorText}`);
    }
    
    const sttData = await sttResp.json();
    console.log('STT Data received:', sttData);
    
    const text = (sttData.text || '').trim();
    transcriptEl.textContent = text;
    console.log('Transcribed text:', text);
    
    if (!text) {
      console.log('No text transcribed, skipping LLM call');
      return;
    }

    // --- INTENT / LLM ---
    console.log('Sending to LLM...');
    intentAbort = new AbortController();
    
    const ir = await fetch(`${ORIGIN}${API_PREFIX}/determine_intent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
      signal: intentAbort.signal
    });
    
    console.log('LLM Response status:', ir.status);
    
    if (!ir.ok) {
      const errorText = await ir.text();
      console.error('[LLM HTTP Error]', ir.status, errorText);
      throw new Error(`LLM failed: ${ir.status} ${errorText}`);
    }
    
    const intent = await ir.json();
    console.log('LLM Response:', intent);
    
    const reply = (intent.result || '').trim();
    if (!reply) {
      console.log('No reply from LLM');
      return;
    }

    lastLLMReply = reply;
    console.log('LLM Reply:', reply);

    // --- TTS ---
    await speak(reply, voiceEl.value || 'alloy');

  } catch(e) {
    if (e.name === 'AbortError') {
      console.log('Pipeline aborted (user spoke again)');
      return;
    }
    console.error('Transcribe/LLM pipeline failed:', e);
    toast('Speech pipeline failed','bad');
  }
}

// ===== Mic start/stop =====
async function start(){
  try{
    stream = await navigator.mediaDevices.getUserMedia({ audio:{ noiseSuppression:true, echoCancellation:true } });
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    source = ctx.createMediaStreamSource(stream);
    analyser = ctx.createAnalyser(); analyser.fftSize = 2048; source.connect(analyser);
    drawScope();
    startBtn.disabled = true; stopBtn.disabled = false;
    micState.textContent = 'armed';
    vadState.textContent = 'ready'; vadState.className='muted';
    toast('Mic ready. Start speaking…','ok');
  }catch(e){
    toast('Microphone blocked', 'bad'); log('getUserMedia error:', e?.message || e);
  }
}
function stop(){
  try{
    cancelAnimationFrame(rafId);
    if (recorder && recorder.state !== 'inactive') recorder.stop();
    if (stream) stream.getTracks().forEach(t=>t.stop());
    if (ctx && ctx.state !== 'closed') ctx.close();
  }catch{}
  startBtn.disabled=false; stopBtn.disabled=true;
  micState.textContent='idle'; vadState.textContent='ready'; vadState.className='muted';
}

// ===== TTS fetch/play (abortable) =====
async function speak(text, voice='alloy'){
  if (!text) return;
  stopTTSLocal();
  ttsAbort = new AbortController();
  try{
    // Make sure AudioContext is active (prevents silent play issues)
    try { if (ctx && ctx.state === 'suspended') await ctx.resume(); } catch {}

    const resp = await fetch(`${ORIGIN}${API_PREFIX}/tts`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ text, voice }),
      signal: ttsAbort.signal
    });
    const body = await resp.arrayBuffer().catch(async () => {
      const t = await resp.text(); throw new Error(`Bad TTS: ${resp.status} ${t}`);
    });
    if (!resp.ok) throw new Error(`TTS HTTP ${resp.status}`);
    if (!body.byteLength) throw new Error('Empty audio');

    const blob = new Blob([body], { type:'audio/mpeg' });
    ttsBlobURL = URL.createObjectURL(blob);
    player.pause(); player.src = ttsBlobURL; player.load();
    try { await player.play(); } catch {}
  }catch(e){
    if (e.name !== 'AbortError') { log('TTS error:', e?.message || e); toast('TTS failed','bad'); }
  }
}

// ===== UI wiring =====
startBtn.addEventListener('click', start);
stopBtn .addEventListener('click', stop);
speakBtn.addEventListener('click', ()=>speak(ttsTextEl.value.trim(), voiceEl.value||'alloy'));
stopTTSBtn.addEventListener('click', stopTTS);

// keep canvas live for ResizeObserver
scope.addEventListener('click', ()=>{});
new ResizeObserver(()=>{}).observe(scope);
