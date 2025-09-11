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

