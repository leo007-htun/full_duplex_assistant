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
