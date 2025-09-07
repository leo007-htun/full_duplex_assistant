const API_BASE = location.origin; // https://com-cloud.cloud

const btnRecord = document.getElementById('record');
const btnStop   = document.getElementById('stop');
const transcriptEl = document.getElementById('transcript');
const ttsTextEl = document.getElementById('ttsText');
const voiceEl = document.getElementById('voice');
const speakBtn = document.getElementById('speak');
const player = document.getElementById('player');
const logEl = document.getElementById('log');

let mediaRecorder;
let chunks = [];

function log(...args) {
  console.log(...args);
  logEl.textContent += args.map(String).join(' ') + '\n';
}

async function startRecording() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    chunks = [];
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });

    mediaRecorder.ondataavailable = e => {
      if (e.data && e.data.size > 0) chunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
      try {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const fd = new FormData();
        fd.append('file', blob, 'input.webm');

        const resp = await fetch(`${API_BASE}/api/transcribe`, {
          method: 'POST',
          body: fd,
        });

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(`Transcribe failed: ${resp.status} ${resp.statusText} ${JSON.stringify(err)}`);
        }

        const data = await resp.json();
        transcriptEl.textContent = data.text || '';
        log('Transcription OK');
      } catch (err) {
        log('Transcription error:', err.message || err);
        alert('Transcription error. See log.');
      }
    };

    mediaRecorder.start();
    btnRecord.disabled = true;
    btnStop.disabled = false;
    log('Recording…');
  } catch (err) {
    log('Mic error:', err.message || err);
    alert('Could not access microphone. Check permissions.');
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
    mediaRecorder.stream.getTracks().forEach(t => t.stop());
    btnRecord.disabled = false;
    btnStop.disabled = true;
    log('Stopped.');
  }
}

async function speakText() {
  const text = ttsTextEl.value.trim();
  const voice = voiceEl.value || 'alloy';
  if (!text) return;

  try {
    const resp = await fetch(`${API_BASE}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(`TTS failed: ${resp.status} ${resp.statusText} ${JSON.stringify(err)}`);
    }

    const mime = resp.headers.get('content-type') || 'audio/mpeg';
    const buf = await resp.arrayBuffer();
    const blob = new Blob([buf], { type: mime });
    const url = URL.createObjectURL(blob);

    // Load into the audio element and play
    player.src = url;
    try {
      await player.play();
      log('Playing TTS audio.');
    } catch (playErr) {
      // Autoplay might be blocked; user can press play
      log('Autoplay blocked, click play on the audio control.');
    }
  } catch (err) {
    log('TTS error:', err.message || err);
    alert('TTS error. See log.');
  }
}

btnRecord.addEventListener('click', startRecording);
btnStop.addEventListener('click', stopRecording);
speakBtn.addEventListener('click', speakText);

// Optional: quick env check
(async () => {
  try {
    const r = await fetch(`${API_BASE}/api/healthz`);
    const j = await r.json();
    log('Health:', JSON.stringify(j));
  } catch (e) {
    log('Health check failed', e.message || e);
  }
})();
