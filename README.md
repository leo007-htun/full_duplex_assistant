# Real-Time Full-Duplex Voice Assistant <img alt="🎙️ Live Demo — com-cloud.cloud" src="https://img.shields.io/badge/%F0%9F%8E%99%EF%B8%8F%20Live%20Demo-com--cloud.cloud-orange?style=for-the-badge"/> </p>

Low-latency, interruptible, **full-duplex** (talk & listen at the same time) voice assistant with a web UI, streaming ASR, TTS, and LLM orchestration. Built for real conversations, barge-in, and hands-free control.

<p align="center">
  <img alt="full duplex assistant banner" src="https://img.shields.io/badge/voice-full--duplex-4A90E2">
  <img alt="docker compose" src="https://img.shields.io/badge/docker-compose-0db7ed">
  <img alt="realtime" src="https://img.shields.io/badge/latency-~low-brightgreen">
  <a href="https://com-cloud.cloud" target="_blank" rel="noopener noreferrer">
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

