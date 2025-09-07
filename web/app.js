const API_BASE = location.origin; // https://com-cloud.cloud

// UI refs
const statusEl = document.getElementById('status');
const apiEl = document.getElementById('api');
const micStateEl = document.getElementById('micState');
const vadStateEl = document.getElementById('vadState');
const btnRecord = document.getElementById('record');
const btnStop = document.getElementById('stop');
const transcriptEl = document.getElementById('transcript');
const ttsTextEl = document.getElementById('ttsText');
const voiceEl = document.getElementById('voice');
const speakBtn = document.getElementById('speak');
const player = document.getElementById('player');
const logEl = document.getElementById('log');
const kChunks = document.getElementById('kChunks');
const kBytes = document.getElementById('kBytes');
const kMs = document.getElementById('kMs');
const scope = document.getElementById('scope');
const levelFill = document.getElementById('level');
const mimeSel = document.getElementById('mime');
const toastEl = document.getElementById('toast');

apiEl.textContent = '/api';

// Toast helper
let toastTimer;
function toast(msg, cls=''){
  clearTimeout(toastTimer);
  toastEl.className = `toast show ${cls}`;
  toastEl.textContent = msg;
  toastTimer = setTimeout(()=> toastEl.className='toast', 2700);
}

// Logging helper
function log(...args){
  console.log(...args);
  logEl.textContent += args.map(a => typeof a==='string' ? a : JSON.stringify(a)).join(' ') + '\n';
  logEl.scrollTop = logEl.scrollHeight;
}

// Health check
(async () => {
  try{
    const r = await fetch(`${API_BASE}/api/healthz`);
    const j = await r.json();
    if (j?.ok) {
      statusEl.textContent = 'Online';
      statusEl.className = 'ok';
    } else {
      statusEl.textContent = 'Degraded';
      statusEl.className = 'warn';
    }
  }catch(e){
    statusEl.textContent = 'Offline';
    statusEl.className = 'bad';
  }
})();

// Recorder, analyser, scope
let mediaRecorder, mediaStream, audioCtx, analyser, rafId;
let chunks = [];
let bytes = 0;
let startedAt = 0;

function setupAnalyser(stream){
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  const source = audioCtx.createMediaStreamSource(stream);
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);

  const canvas = scope;
  const c = canvas.getContext('2d');
  function draw(){
    rafId = requestAnimationFrame(draw);
    const w = canvas.width = canvas.clientWidth;
    const h = canvas.height = canvas.clientHeight;
    c.clearRect(0,0,w,h);
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(data);

    // Level bar
    let peak = 0;
    for (let i=0;i<data.length;i++){
      const v = Math.abs(data[i]-128);
      if (v>peak) peak = v;
    }
    const pct = Math.min(100, Math.round((peak/128)*100));
    levelFill.style.width = `${pct}%`;

    // Oscilloscope
    c.lineWidth = 2;
    c.strokeStyle = 'rgba(76,201,240,.9)';
    c.beginPath();
    const slice = w / data.length;
    for(let i=0;i<data.length;i++){
      const x = i * slice;
      const y = (data[i]/255)*h;
      if(i===0) c.moveTo(x,y); else c.lineTo(x,y);
    }
    c.stroke();

    // Baseline
    c.strokeStyle = 'rgba(255,255,255,.08)';
    c.beginPath();
    c.moveTo(0,h/2); c.lineTo(w,h/2); c.stroke();
  }
  draw();
}

async function startRecording(){
  try{
    const mimeType = mimeSel.value;
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    setupAnalyser(mediaStream);

    chunks = []; bytes = 0; startedAt = performance.now();
    mediaRecorder = new MediaRecorder(mediaStream, { mimeType });

    mediaRecorder.ondataavailable = e => {
      if (e.data && e.data.size > 0){
        chunks.push(e.data);
        bytes += e.data.size;
        kChunks.textContent = String(chunks.length);
        kBytes.textContent = `${(bytes/1024).toFixed(1)} KB`;
      }
    };

    mediaRecorder.onstop = async () => {
      cancelAnimationFrame(rafId);
      if (audioCtx) { try { audioCtx.close(); } catch {} }
      const blob = new Blob(chunks, { type: mimeType });
      const ms = Math.max(0, Math.round(performance.now() - startedAt));
      kMs.textContent = `${ms} ms`;

      if (!blob || blob.size === 0){
        toast('No audio captured', 'bad');
        return;
      }

      const fd = new FormData();
      fd.append('file', blob, `input.${mimeType.split('/')[1] || 'webm'}`);

      try{
        micStateEl.textContent = 'uploading';
        const resp = await fetch(`${API_BASE}/api/transcribe`, { method:'POST', body: fd });
        if (!resp.ok){
          let detail = await resp.text();
          try { detail = JSON.stringify(JSON.parse(detail)); } catch {}
          throw new Error(`${resp.status} ${resp.statusText} ${detail}`);
        }
        const data = await resp.json();
        transcriptEl.textContent = data.text || '';
        toast('Transcription complete', 'ok');
      }catch(err){
        log('Transcribe error:', err?.message || err);
        toast('Transcription failed', 'bad');
      }finally{
        micStateEl.textContent = 'idle';
      }
    };

    mediaRecorder.start(100); // gather chunks every 100ms
    btnRecord.disabled = true;
    btnStop.disabled = false;
    micStateEl.textContent = 'recording';
    vadStateEl.textContent = 'server';
    toast('Recording…', 'ok');
  }catch(err){
    log('Mic error:', err?.message || err);
    toast('Microphone permission error', 'bad');
  }
}

function stopRecording(){
  try{
    if (mediaRecorder && mediaRecorder.state !== 'inactive'){
      mediaRecorder.stop();
    }
  }finally{
    if (mediaStream){
      mediaStream.getTracks().forEach(t => t.stop());
    }
    btnRecord.disabled = false;
    btnStop.disabled = true;
  }
}

async function speakText(){
  const text = ttsTextEl.value.trim();
  const voice = voiceEl.value || 'alloy';
  if (!text) return toast('Enter text to speak', 'warn');

  try{
    const resp = await fetch(`${API_BASE}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type':'application/json' },
      body: JSON.stringify({ text, voice }),
    });

    const ct = resp.headers.get('content-type') || '';
    if (!resp.ok){
      let detail = await resp.text();
      try { detail = JSON.stringify(JSON.parse(detail)); } catch {}
      throw new Error(`${resp.status} ${resp.statusText} ${detail}`);
    }
    const buf = await resp.arrayBuffer();
    if (!buf || buf.byteLength === 0) throw new Error('Empty audio buffer');

    const blob = new Blob([buf], { type: 'audio/mpeg' });
    if (blob.size === 0) throw new Error('Zero-length MP3 blob');

    const url = URL.createObjectURL(blob);
    player.pause();
    player.removeAttribute('src');
    player.load();
    player.src = url;
    player.load();

    player.onended = () => URL.revokeObjectURL(url);

    try{
      await player.play();
      toast('Playing speech…', 'ok');
      log('TTS bytes:', buf.byteLength, 'ctype:', ct);
    }catch{
      toast('Autoplay blocked — click play', 'warn');
    }
  }catch(err){
    log('TTS error:', err?.message || err);
    toast('TTS failed', 'bad');
  }
}

// Events
btnRecord.addEventListener('click', startRecording);
btnStop.addEventListener('click', stopRecording);
speakBtn.addEventListener('click', speakText);

// Resize redraw (canvas sized via CSS)
new ResizeObserver(() => {
  if (analyser && scope) { /* next draw loop picks up size */ }
}).observe(scope);
