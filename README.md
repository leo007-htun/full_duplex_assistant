# Real-Time Full-Duplex Voice Assistant

Low-latency, interruptible, **full-duplex** (talk & listen at the same time) voice assistant with a web UI, streaming ASR, TTS, and LLM orchestration. Built for real conversations, barge-in, and hands-free control.

<p align="center">
  <img alt="full duplex assistant banner" src="https://img.shields.io/badge/voice-full--duplex-4A90E2">
  <img alt="docker compose" src="https://img.shields.io/badge/docker-compose-0db7ed">
  <img alt="realtime" src="https://img.shields.io/badge/latency-~low-brightgreen">
</p>

## ✨ Features

- **Full-duplex audio**: speak over the assistant; it adapts in real time (barge-in / interruption).
- **Streaming ASR**: incremental transcripts while you talk.
- **Streaming TTS**: the assistant starts speaking before the full text is ready.
- **LLM orchestration**: tool use/function calls and stateful dialog.
- **Web UI**: in-browser mic capture, live waveforms, partial captions.
- **Containerized**: one-command up via `docker compose`.
- **Reverse proxy**: Nginx configuration included for clean paths and TLS termination.

---

## 🧭 Architecture (at a glance)
Browser (Web UI)
├─ Mic capture (WebAudio) → WebSocket → ASR Ingress
│ │
│ partial transcripts
│ ▼
├─ Live captions ← ASR (streaming)
│ │
│ ▼
├─ TTS audio playback ← TTS (streaming chunks)
│ ▲
│ │
└─ Controls/Events → Orchestrator (LLM, tools, memory)
│


Typical services:
- **web**: static SPA / UI dev server.
- **api/orchestrator**: websocket endpoints for audio in/out + LLM routing.
- **asr**: streaming speech-to-text backend (or cloud API).
- **tts**: text-to-speech streamer (or cloud API).
- **nginx**: reverse proxy (`/ws`, `/api`, static).

---

## 🚀 Quick Start

### 1) Prereqs
- Docker & Docker Compose
- At least one ASR + TTS provider API key (e.g., OpenAI Realtime, Deepgram, Whisper server, ElevenLabs, etc.).
- One LLM provider key.

### 2) Configure environment

Create a `.env` at the repo root (example—rename keys to your providers):

```bash
# LLM / Orchestrator
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# ASR
ASR_PROVIDER=openai_realtime   # or deepgram, local-whisper, etc.
ASR_API_KEY=...

# TTS
TTS_PROVIDER=openai_realtime   # or elevenlabs, edge, etc.
TTS_API_KEY=...

# CORS / ORIGINS
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000

# Optional
LOG_LEVEL=info
3) Bring up the stack
docker compose up --build


Web UI: http://localhost
 (or whichever port your web service exposes)

WebSocket endpoints: proxied via Nginx (e.g., /ws/asr, /ws/tts, /ws/assistant)

REST endpoints: proxied via Nginx (e.g., /api/*)

🖥️ Local Dev (without Docker)

Use this if you prefer running services directly.

Backend

cd src
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


Exposes REST + WS endpoints at http://localhost:8000.

Web UI

cd web
npm i
npm run dev


Set the UI .env (e.g., VITE_API_BASE=http://localhost:8000).

Nginx (optional)

Use the provided nginx/conf.d/*.conf as reference if you want local reverse proxying.

🎙️ Using the App

Open the web UI.

Click Connect (if required) to establish the WebSocket session.

Press Hold-to-talk or Start to stream mic audio.

Speak naturally; interrupt the assistant at any time.

Watch live captions and waveforms; hear streaming TTS playback.

⚙️ Configuration

Common knobs (env or config files):

ASR: model name, language hints, VAD sensitivity, chunk size (ms).

TTS: voice, speed, sample rate, chunk size.

LLM: model, temperature, function/tool schemas, max tokens.

Transport: WebSocket buffer size, keep-alive, heartbeat.

Nginx: TLS, HTTP/2, WebSocket upgrade headers.

🔌 API (typical)

Endpoints may differ; update these to match your code.

GET /healthz – service health.

WS /ws/asr – binary PCM/Opus in ↔ partial transcripts out (JSON).

WS /ws/assistant – bidirectional control: user events, tool calls, assistant responses.

WS /ws/tts – text in ↔ audio frames out.

POST /api/tools/<name> – server-side tools/functions (search, DB, home-automation, etc.).

🔐 Security

Microphone access is user-mediated in the browser.

Set CORS and allowed origins.

Put all public endpoints behind TLS (configure Nginx with certificates).

Keep provider API keys server-side (never embed in the web app).

🧪 Testing

Unit: mock ASR/TTS/LLM providers, assert dialog state transitions.

Latency: measure end-to-end (speech-start → first audio frame).

Barge-in: simulate user interjection while TTS is streaming.

📦 Deployment

Docker Compose on a single VM.

Reverse proxy with Nginx (HTTP/2 + WebSocket upgrades).

Optional: systemd unit to auto-start docker compose after reboot.

Cloud storage/CDN for static assets in web/.

🗺️ Roadmap

 Wake-word (keyword spotting) in browser

 Speaker diarization & VAD tuning presets

 Pluggable tool registry (calendar, notes, smart-home)

 Session persistence & transcripts export

 Multi-voice TTS & prosody controls

🤝 Contributing

Fork & create a feature branch.

Keep PRs small and focused.

Include screenshots or short clips for UX changes.

Add tests where sensible.

