Skip to content
Chat history

You said:
https://github.com/leo007-htun/full_duplex_assistant

write readme.md for this
ChatGPT said:

Thought for 17s
Here’s a clean, production-ready README.md for your repo. If you want me to tailor any section (env vars, ports, deployment targets) to your exact code, just paste your docker-compose.yml and src/ layout and I’ll align it precisely.

Real-Time Full-Duplex Voice Assistant
Low-latency, interruptible, full-duplex (talk & listen at the same time) voice assistant with a web UI, streaming ASR, TTS, and LLM orchestration. Built for real conversations, barge-in, and hands-free control. 
GitHub

<p align="center"> <img alt="full duplex assistant banner" src="https://img.shields.io/badge/voice-full--duplex-4A90E2"> <img alt="docker compose" src="https://img.shields.io/badge/docker-compose-0db7ed"> <img alt="realtime" src="https://img.shields.io/badge/latency-~low-brightgreen"> </p>
✨ Features
Full-duplex audio: speak over the assistant; it adapts in real time (barge-in / interruption).

Streaming ASR: incremental transcripts while you talk.

Streaming TTS: the assistant starts speaking before the full text is ready.

LLM orchestration: tool use/function calls and stateful dialog.

Web UI: in-browser mic capture, live waveforms, partial captions.

Containerized: one-command up via docker compose.

Reverse proxy: Nginx configuration included for clean paths and TLS termination.

Repo structure suggests src/, web/, nginx/conf.d/, and a root docker-compose.yml. Adjust commands below if you’ve customized paths. 
GitHub

🧭 Architecture (at a glance)
Browser (Web UI)
  ├─ Mic capture (WebAudio) → WebSocket →  ASR Ingress
  │                                │
  │                      partial transcripts
  │                                ▼
  ├─ Live captions       ←  ASR (streaming)
  │                                │
  │                                ▼
  ├─ TTS audio playback  ←  TTS (streaming chunks)
  │                                ▲
  │                                │
  └─ Controls/Events  →  Orchestrator (LLM, tools, memory)
                               │
                     optional function/tool calls
Typical services:

web: static SPA / UI dev server.

api/orchestrator: websocket endpoints for audio in/out + LLM routing.

asr: streaming speech-to-text backend (or cloud API).

tts: text-to-speech streamer (or cloud API).

nginx: reverse proxy (/ws, /api, static).

🚀 Quick Start
1) Prereqs
Docker & Docker Compose

At least one ASR + TTS provider API key (e.g., OpenAI Realtime, Deepgram, Whisper server, ElevenLabs, etc.).

One LLM provider key.

2) Configure environment
Create a .env at the repo root (example—rename keys to your providers):

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
If your docker-compose.yml expects different variable names, mirror them here.

3) Bring up the stack
docker compose up --build
Web UI: http://localhost (or whichever port your web service exposes)

WebSocket endpoints: proxied via Nginx (e.g., /ws/asr, /ws/tts, /ws/assistant)

REST endpoints: proxied via Nginx (e.g., /api/*)

Check container logs if a service fails to bind. Ports may be defined in nginx/conf.d and the compose file. 
GitHub

🖥️ Local Dev (without Docker)
Use this if you prefer running services directly.

Backend

Create a Python venv and install requirements:

cd src
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Exposes REST + WS endpoints at http://localhost:8000.

Web UI

Typical flow for Vite/React (adjust to your framework):

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

📄 License
Add a LICENSE file (MIT/Apache-2.0 recommended). If one already exists in the repo, this section will reflect that.

🙏 Acknowledgements
Thanks to the growing ecosystem around real-time ASR/TTS/LLM and OSS tooling. If you relied on specific providers or libraries, list them here.

Links
Project repo: this page. 
GitHub

If you share the actual service names and ports from your docker-compose.yml, I’ll align the README’s commands/endpoints exactly to your setup.

You said:
give me markdown for all of this
ChatGPT said:
Got it 👍 — here’s the entire README fully formatted in Markdown:

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
optional function/tool calls


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
Web UI: http://localhost (or whichever port your web service exposes)

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

📄 License
Add a LICENSE file (MIT/Apache-2.0 recommended). If one already exists in the repo, this section will reflect that.

🙏 Acknowledgements
Thanks to the growing ecosystem around real-time ASR/TTS/LLM and OSS tooling. If you relied on specific providers or libraries, list them here.


Would you like me to **match the README endpoints and service names exactly** to your `docker-compose.yml` (e.g., if your API is `assistant:8000`, web is `5173`, etc.)? That way the setup instructions won’t be generic but will be copy-paste runnable for your repo.
You said:
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
- **Containerized**: one-command up via docker compose.
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
- **nginx**: reverse proxy (/ws, /api, static).

---

## 🚀 Quick Start

### 1) Prereqs
- Docker & Docker Compose
- At least one ASR + TTS provider API key (e.g., OpenAI Realtime, Deepgram, Whisper server, ElevenLabs, etc.).
- One LLM provider key.

### 2) Configure environment

Create a .env at the repo root (example—rename keys to your providers):


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


put com-cloud.cloud ad clickale link with icon servring there
ChatGPT said:
Got it ✅ You want to add your domain com-cloud.cloud as a clickable link with an icon (badge-style like the others). Here’s your README with that included:

# Real-Time Full-Duplex Voice Assistant

Low-latency, interruptible, **full-duplex** (talk & listen at the same time) voice assistant with a web UI, streaming ASR, TTS, and LLM orchestration. Built for real conversations, barge-in, and hands-free control.

<p align="center">
  <img alt="full duplex assistant banner" src="https://img.shields.io/badge/voice-full--duplex-4A90E2">
  <img alt="docker compose" src="https://img.shields.io/badge/docker-compose-0db7ed">
  <img alt="realtime" src="https://img.shields.io/badge/latency-~low-brightgreen">
  <a href="https://com-cloud.cloud" target="_blank">
    <img alt="com-cloud.cloud" src="https://img.shields.io/badge/visit-com--cloud.cloud-orange?logo=icloud">
  </a>
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
optional function/tool calls


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
Web UI: http://localhost (or whichever port your web service exposes)

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

📄 License
Add a LICENSE file (MIT/Apache-2.0 recommended). If one already exists in the repo, this section will reflect that.

🙏 Acknowledgements
Thanks to the growing ecosystem around real-time ASR/TTS/LLM and OSS tooling. If you relied on specific providers or libraries, list them here.


Do you want the **`com-cloud.cloud` badge** to always appear centered with the other badges (like now), or should I also add it again as a **dedicated “🌐 Live Demo” section** further down with a bigger button-style link?
You said:
version: "3.9"

services:
  init_letsencrypt:
    image: alpine:3.20
    command: sh -c "mkdir -p /letsencrypt && touch /letsencrypt/acme.json && chmod 600 /letsencrypt/acme.json"
    volumes:
      - ./letsencrypt:/letsencrypt
    restart: "no"

  traefik:
    image: traefik:v3.0
    depends_on:
      init_letsencrypt:
        condition: service_completed_successfully
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      - --entrypoints.websecure.address=:443
      - --entrypoints.web.http.redirections.entryPoint.to=websecure
      - --entrypoints.web.http.redirections.entryPoint.scheme=https

      # Long-lived WS/streams (tune if you like)
      - --entryPoints.websecure.transport.respondingTimeouts.idleTimeout=0
      - --serversTransport.forwardingTimeouts.idleConnTimeout=0

      # Let's Encrypt (TLS-ALPN challenge; switch to httpchallenge if behind a LB/CDN)
      - --certificatesresolvers.letsencrypt.acme.email=${LE_EMAIL}
      - --certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json
      - --certificatesresolvers.letsencrypt.acme.tlschallenge=true

      # (optional) dashboard off
      - --api.dashboard=false
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./letsencrypt:/letsencrypt
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks: [web]
    restart: unless-stopped

  web:
    image: nginx:alpine
    volumes:
      - ./web:/usr/share/nginx/html:ro
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=web"
      # Serve static site for everything except /api and /ws
      - "traefik.http.routers.web.rule=Host(com-cloud.cloud) && PathPrefix(/) && !PathPrefix(/api) && !PathPrefix(/ws)"
      - "traefik.http.routers.web.entrypoints=websecure"
      - "traefik.http.routers.web.tls=true"
      - "traefik.http.routers.web.tls.certresolver=letsencrypt"
      - "traefik.http.routers.web.priority=1"
      - "traefik.http.services.web.loadbalancer.server.port=80"
    networks: [web]
    restart: unless-stopped

  assistant:
    image: sithuyehtun/full_duplex_assistant:${IMAGE_TAG:-latest}
    command: >
      uvicorn assistant.app:app
      --host 0.0.0.0
      --port 8000
      --proxy-headers
      --forwarded-allow-ips=127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
    env_file:
      - ./src/assistant/.env
    environment:
      - ENABLE_VOICE=0
      - ALLOWED_ORIGINS=https://com-cloud.cloud
    expose:
      - "8000"
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=web"

      # ===== WebSocket router (if your app exposes /ws) =====
      - "traefik.http.routers.ws.rule=Host(com-cloud.cloud) && PathPrefix(/ws)"
      - "traefik.http.routers.ws.entrypoints=websecure"
      - "traefik.http.routers.ws.tls=true"
      - "traefik.http.routers.ws.tls.certresolver=letsencrypt"
      - "traefik.http.routers.ws.priority=100"
      - "traefik.http.routers.ws.service=assistant-svc"
      - "traefik.http.services.assistant-svc.loadbalancer.server.port=8000"

      # ===== REST router =====
      - "traefik.http.routers.api.rule=Host(com-cloud.cloud) && PathPrefix(/api)"
      - "traefik.http.routers.api.entrypoints=websecure"
      - "traefik.http.routers.api.tls=true"
      - "traefik.http.routers.api.tls.certresolver=letsencrypt"
      - "traefik.http.routers.api.priority=50"
      - "traefik.http.routers.api.service=assistant-svc"

      # Strip /api before hitting FastAPI
      - "traefik.http.middlewares.api-strip.stripprefix.prefixes=/api"
      # Basic rate limit for token mint
      - "traefik.http.middlewares.api-ratelimit.ratelimit.average=10"
      - "traefik.http.middlewares.api-ratelimit.ratelimit.burst=20"
      - "traefik.http.routers.api.middlewares=api-strip,api-ratelimit"
    healthcheck:
      test:
        ["CMD-SHELL", "wget -qO- http://127.0.0.1:8000/healthz >/dev/null 2>&1 || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
    networks: [web]
    restart: unless-stopped

networks:
  web:
    driver: bridge


this is my docker tech stack

write mark down for this
ChatGPT said:

Stopped thinking
You said:
update my mark down for readme.md
ChatGPT said:
Perfect — now that I see your docker-compose.yml, I’ll update your README so it’s aligned with your actual Traefik + Nginx + Assistant stack and your domain com-cloud.cloud.

Here’s the improved README.md in full Markdown:

# Real-Time Full-Duplex Voice Assistant

Low-latency, interruptible, **full-duplex** (talk & listen at the same time) voice assistant with a web UI, streaming ASR, TTS, and LLM orchestration. Built for real conversations, barge-in, and hands-free control.

<p align="center">
  <img alt="full duplex assistant banner" src="https://img.shields.io/badge/voice-full--duplex-4A90E2">
  <img alt="docker compose" src="https://img.shields.io/badge/docker-compose-0db7ed">
  <img alt="realtime" src="https://img.shields.io/badge/latency-~low-brightgreen">
  <a href="https://com-cloud.cloud" target="_blank">
    <img alt="com-cloud.cloud" src="https://img.shields.io/badge/live-demo-com--cloud.cloud-orange?logo=icloud">
  </a>
</p>

---

## ✨ Features

- **Full-duplex audio**: talk and listen simultaneously (barge-in / interruption supported).
- **Streaming ASR**: incremental transcripts while you speak.
- **Streaming TTS**: assistant responds with audio before text finishes.
- **LLM orchestration**: tool use/function calls and stateful dialog.
- **Web UI**: mic capture, waveforms, and live captions in-browser.
- **Production-ready stack**: Traefik reverse proxy + auto TLS, Nginx static hosting, FastAPI backend.
- **Single command up**: deploy with `docker compose up -d`.

---

## 🧭 Architecture

Browser (Web UI)
├─ Mic capture (WebAudio) → WebSocket → Assistant (FastAPI)
│ │
│ partial transcripts
│ ▼
├─ Live captions ← ASR (streaming via Assistant)
│ │
│ ▼
├─ TTS audio playback ← TTS (streaming chunks)
│ ▲
│ │
└─ Controls/Events → LLM Orchestrator
│
optional function/tool calls


**Services in this repo**:

- **traefik**: reverse proxy, automatic HTTPS via Let’s Encrypt.
- **web**: static frontend (served by Nginx).
- **assistant**: FastAPI backend (ASR, TTS, LLM orchestration, WebSockets).
- **init_letsencrypt**: bootstrap storage for ACME certificates.

---

## 🚀 Quick Start

### 1. Prerequisites
- Docker & Docker Compose
- Domain pointing to your server: [`com-cloud.cloud`](https://com-cloud.cloud)
- DNS A/AAAA records configured
- API keys for ASR, TTS, and LLM providers

### 2. Configure Environment

Create `src/assistant/.env` with your secrets:

```bash
# LLM / Orchestrator
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...

# ASR
ASR_PROVIDER=openai_realtime
ASR_API_KEY=...

# TTS
TTS_PROVIDER=openai_realtime
TTS_API_KEY=...

# CORS / ORIGINS
ALLOWED_ORIGINS=https://com-cloud.cloud

# Optional
LOG_LEVEL=info
Set your email for Let’s Encrypt in .env at the root:

LE_EMAIL=you@example.com
IMAGE_TAG=latest
3. Start the stack
docker compose up -d
That’s it!

Frontend: https://com-cloud.cloud

API: https://com-cloud.cloud/api/

WebSockets: wss://com-cloud.cloud/ws/

🖥️ Local Development
Run backend directly:

cd src/assistant
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn assistant.app:app --reload --host 0.0.0.0 --port 8000
Frontend:

cd web
npm install
npm run dev
🎙️ Using the Assistant
Open https://com-cloud.cloud.

Click Connect to establish WebSocket session.

Press Hold-to-talk or Start to stream mic audio.

Speak naturally; interrupt the assistant mid-sentence.

Watch live captions, hear real-time TTS playback.

⚙️ Configuration
Key options:

ASR: model, language hints, VAD sensitivity.

TTS: voice, speed, sample rate.

LLM: model, temperature, tool schemas.

Traefik: TLS challenge type, timeouts, rate limits.

🔌 API
GET /healthz – service health

WS /ws/asr – audio in ↔ transcript out

WS /ws/assistant – dialog orchestration (events + responses)

WS /ws/tts – text in ↔ audio out

POST /api/tools/<name> – trigger server-side tool functions

🔐 Security
HTTPS enforced (TLS via Let’s Encrypt + Traefik).

Strict CORS (limited to https://com-cloud.cloud).

API rate limiting enabled (/api).

Secrets kept in .env (not in frontend).

📦 Deployment Notes
Reverse proxy: Traefik v3 with ACME TLS challenge.

Certificates stored in ./letsencrypt/acme.json.

Static frontend served by Nginx (web service).

Backend served via assistant (FastAPI) behind Traefik.

Scale with Docker Swarm / k8s if needed.

🗺️ Roadmap
 Wake-word hotword detection

 Speaker diarization

 Plug-and-play tool registry

 Persistent transcripts

 Multi-voice TTS

🤝 Contributing
Fork this repo

Create a feature branch

Submit PR with screenshots/logs if UI/backend affected

📄 License
Add a LICENSE file (MIT/Apache-2.0 suggested).

🙏 Acknowledgements
Thanks to the open-source ecosystem around ASR, TTS, and LLMs that makes real-time conversational AI possible.

<p align="center"> 👉 <a href="https://com-cloud.cloud" target="_blank"><b>Try the Live Demo</b></a> </p> ```
Would you like me to also add a diagram of your Docker services (traefik ↔ web ↔ assistant) as an ASCII block under the Architecture section, so readers see how Traefik routes traffic to /api, /ws, and /?

You said:
yes please
ChatGPT said:
Great idea 🚀 — I’ll add an ASCII diagram of your Docker stack showing how Traefik routes requests to web (Nginx static site) and assistant (FastAPI backend).

Here’s your updated README.md with the new diagram included:

# Real-Time Full-Duplex Voice Assistant

Low-latency, interruptible, **full-duplex** (talk & listen at the same time) voice assistant with a web UI, streaming ASR, TTS, and LLM orchestration. Built for real conversations, barge-in, and hands-free control.

<p align="center">
  <img alt="full duplex assistant banner" src="https://img.shields.io/badge/voice-full--duplex-4A90E2">
  <img alt="docker compose" src="https://img.shields.io/badge/docker-compose-0db7ed">
  <img alt="realtime" src="https://img.shields.io/badge/latency-~low-brightgreen">
  <a href="https://com-cloud.cloud" target="_blank">
    <img alt="com-cloud.cloud" src="https://img.shields.io/badge/live-demo-com--cloud.cloud-orange?logo=icloud">
  </a>
</p>

---

## ✨ Features

- **Full-duplex audio**: talk and listen simultaneously (barge-in / interruption supported).
- **Streaming ASR**: incremental transcripts while you speak.
- **Streaming TTS**: assistant responds with audio before text finishes.
- **LLM orchestration**: tool use/function calls and stateful dialog.
- **Web UI**: mic capture, waveforms, and live captions in-browser.
- **Production-ready stack**: Traefik reverse proxy + auto TLS, Nginx static hosting, FastAPI backend.
- **Single command up**: deploy with `docker compose up -d`.

---

## 🧭 Architecture

### Application Flow

Browser (Web UI)
├─ Mic capture (WebAudio) → WebSocket → Assistant (FastAPI)
│ │
│ partial transcripts
│ ▼
├─ Live captions ← ASR (streaming via Assistant)
│ │
│ ▼
├─ TTS audio playback ← TTS (streaming chunks)
│ ▲
│ │
└─ Controls/Events → LLM Orchestrator
│
optional function/tool calls


### Docker Stack & Routing

               ┌───────────────────────────┐
               │        Internet            │
               └────────────┬──────────────┘
                            │  :80 / :443
                            ▼
                   ┌─────────────────┐
                   │     Traefik     │
                   │ (Reverse Proxy) │
                   └───────┬─────────┘
             ┌─────────────┼─────────────┐
             │             │



No file chosenNo file chosen
ChatGPT can make mistakes. Check important info. See Cookie Preferences.
ChatGPT is still generating a response...
