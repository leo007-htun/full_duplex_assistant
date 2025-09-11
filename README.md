<!-- Title + Live Demo badge (centered) -->
<h1 align="center">
  Real-Time Full-Duplex Voice Assistant
  &nbsp;
  <a href="https://com-cloud.cloud" target="_blank" rel="noopener">
    <img alt="🎙️ Live Demo — com-cloud.cloud"
         src="https://img.shields.io/badge/%F0%9F%8E%99%EF%B8%8F%20Live%20Demo-com--cloud.cloud-orange?style=for-the-badge">
  </a>
</h1>

<!-- Demo video (centered) -->
<p align="center">
  <a href="https://youtu.be/ioz0FZOchUY" target="_blank" rel="noopener">
    <img src="https://img.youtube.com/vi/ioz0FZOchUY/hqdefault.jpg" alt="Watch the demo" width="800">
  </a>
</p>




<p align="center">
  Low-latency, interruptible, <b>full-duplex</b> (talk &amp; listen at the same time) voice assistant with a web UI, streaming ASR, TTS, and LLM orchestration. Built for real conversations, barge-in, and hands-free control.
</p>

<!-- Badges (perfectly centered in two rows) -->
<table align="center">
  <tr>
    <td align="center">
      <a href="https://pypi.org/project/full-duplex-assistant/">
        <img alt="PyPI"
             src="https://img.shields.io/pypi/v/full-duplex-assistant.svg?logo=pypi&label=PyPI&style=for-the-badge">
      </a>&nbsp;
      <a href="https://github.com/leo007-htun/full_duplex_assistant/releases">
        <img alt="JS SDK (latest tag)"
             src="https://img.shields.io/github/v/tag/leo007-htun/full_duplex_assistant?label=JS%20SDK&filter=js-v%2A&style=for-the-badge">
      </a>&nbsp;
      <a href="https://github.com/leo007-htun/full_duplex_assistant/tree/main/sdk-js">
        <img alt="SDK version (from package.json)"
             src="https://img.shields.io/github/package-json/v/leo007-htun/full_duplex_assistant?filename=sdk-js/package.json&label=SDK%20version&style=for-the-badge">
      </a>
    </td>
  </tr>
  <tr>
    <td align="center">
      <a href="#"><img alt="voice full duplex" src="https://img.shields.io/badge/voice-full--duplex-4A90E2?style=for-the-badge"></a>&nbsp;
      <a href="https://docs.docker.com/compose/"><img alt="docker compose" src="https://img.shields.io/badge/docker-compose-0db7ed?logo=docker&logoColor=white&style=for-the-badge"></a>&nbsp;
      <a href="#"><img alt="latency low" src="https://img.shields.io/badge/latency-low-brightgreen?style=for-the-badge"></a>
    </td>
  </tr>
</table>



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

##### Application Flow

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

#### 🐋 Docker Stack & Routing

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
             │             │             │
    ┌────────▼───┐   ┌─────▼─────┐   ┌──▼────────┐
    │   /        │   │   /api    │   │   /ws     │
    │   Web UI   │   │  Assistant│   │ Assistant │
    │ (Nginx)    │   │ (FastAPI) │   │ (FastAPI) │
    └────────────┘   └───────────┘   └───────────┘

  
#### Services in this repo

- **traefik**: reverse proxy, automatic HTTPS via Let’s Encrypt.
- **web**: static frontend (served by Nginx).
- **assistant**: FastAPI backend (ASR, TTS, LLM orchestration, WebSockets).
- **init_letsencrypt**: bootstrap storage for ACME certificates.

---

#### 🚀 Quick Start

##### 1. Prerequisites
- Docker & Docker Compose
- Domain pointing to your server: [`com-cloud.cloud`](https://com-cloud.cloud)
- DNS A/AAAA records configured
- API keys for ASR, TTS, and LLM providers

##### 2. Configure Environment

    Create `src/assistant/.env` with your secrets:

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


##### 3. 🖥️ Local Development

###### Run backend directly:

    cd src/assistant
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn assistant.app:app --reload --host 0.0.0.0 --port 8000

###### Frontend
    cd web
    npm install
    npm run dev

#### 🎙️ Using the Assistant

    Open https://com-cloud.cloud
    
    Click on ORB to Connect to establish WebSocket session.
    
    Speak naturally; interrupt the assistant mid-sentence.
    
    Watch live captions, hear real-time TTS playback.
    
    DONT FOTGET TO CLOSE THE TAB!!!

#### ⚙️ Configuration

    Key options:
    
    ASR: model, language hints, VAD sensitivity.
    
    TTS: voice, speed, sample rate.
    
    LLM: model, temperature, tool schemas.
    
    Traefik: TLS challenge type, timeouts, rate limits.

#### 🔌 API

    GET /healthz – service health
    
    WS /ws/asr – audio in ↔ transcript out
    
    WS /ws/assistant – dialog orchestration (events + responses)
    
    WS /ws/tts – text in ↔ audio out
    
    POST /api/tools/<name> – trigger server-side tool functions

#### 🔐 Security

    HTTPS enforced (TLS via Let’s Encrypt + Traefik).
    
    Strict CORS (limited to https://com-cloud.cloud).
    
    API rate limiting enabled (/api).
    
    Secrets kept in .env (not in frontend).

#### 📦 Deployment Notes

    Reverse proxy: Traefik v3 with ACME TLS challenge.
    
    Certificates stored in ./letsencrypt/acme.json.
    
    Static frontend served by Nginx (web service).
    
    Backend served via assistant (FastAPI) behind Traefik.
    
    Scale with Docker Swarm / k8s if needed.

#### 🗺️ Roadmap

     Wake-word hotword detection
    
     Speaker diarization
    
     Plug-and-play tool registry
    
     Persistent transcripts
    
     Multi-voice TTS

#### 🤝 Contributing

    Fork this repo
    
    Create a feature branch
    
    Submit PR with screenshots/logs if UI/backend affected
