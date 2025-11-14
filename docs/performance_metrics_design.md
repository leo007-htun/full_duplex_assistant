# Performance Metrics & Benchmarking System Design
## Full-Duplex Voice Assistant Pipeline

**Author:** Performance Evaluation Framework
**Date:** 2025-11-14
**System:** com-cloud.cloud Production Pipeline

---

## 1. Executive Summary

This document outlines a comprehensive performance metrics and benchmarking framework for a production full-duplex voice assistant system. The framework is designed to measure and evaluate:

- **End-to-end latency** across the entire voice pipeline
- **Streaming stability** under various network conditions
- **Barge-in responsiveness** and interruption handling
- **System throughput** and concurrent connection capacity
- **Audio quality** metrics (ASR accuracy, TTS naturalness)
- **Robustness** under failure scenarios and edge cases
- **Real-time evaluation** with academic-grade rigor

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Client Browser                           │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │Microphone│ → │ VAD +    │ → │ Resampler│ → │ WebSocket│ →  │
│  │          │   │ Encoder  │   │ 48→16kHz │   │  Client  │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│       ↑              ↓                              ↓           │
│       │         ┌──────────┐                   ┌──────────┐    │
│       │         │3D Visual │                   │  Metrics │    │
│       │         │  Orb     │                   │Collector │    │
│       │         └──────────┘                   └──────────┘    │
│       │                                             ↓           │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │ Speaker  │ ← │PCM Player│ ← │Resampler │ ← │Performance│   │
│  │          │   │AudioWrklt│   │24→48kHz  │   │  Timer   │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              ↕ WSS
┌─────────────────────────────────────────────────────────────────┐
│                    Infrastructure Layer                          │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │ Traefik  │ → │ FastAPI  │ → │  OpenAI  │   │Prometheus│    │
│  │  Proxy   │   │ Backend  │   │ Realtime │   │  +TSDB   │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
│       ↓              ↓              ↓               ↑           │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐    │
│  │  Nginx   │   │ Rate     │   │  Token   │   │  Grafana │    │
│  │  Static  │   │ Limiter  │   │  Minter  │   │Dashboard │    │
│  └──────────┘   └──────────┘   └──────────┘   └──────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Metrics Taxonomy

### 3.1 Latency Metrics (Critical Path)

#### A. End-to-End Latency Components

| Metric ID | Component | Definition | Target | Measurement Point |
|-----------|-----------|------------|--------|-------------------|
| **L1** | Microphone Capture Latency | Time from sound wave to digitized audio buffer | <20ms | Browser AudioContext |
| **L2** | Audio Processing Latency | VAD + resampling + encoding time | <10ms | ScriptProcessor callback |
| **L3** | Client Network Latency | Audio chunk transmission to OpenAI | <50ms | WebSocket send timestamp |
| **L4** | ASR Processing Latency | Speech-to-text transcription time | <200ms | OpenAI API internal |
| **L5** | LLM Processing Latency | Text generation first token time (TTFT) | <300ms | response.created event |
| **L6** | TTS Processing Latency | Text-to-audio synthesis first chunk | <200ms | audio.delta event |
| **L7** | Audio Download Latency | TTS audio chunk network transmission | <30ms | WebSocket receive |
| **L8** | Audio Rendering Latency | Decode + resample + enqueue to AudioWorklet | <20ms | PCM player processing |
| **L9** | Speaker Output Latency | AudioContext output buffer delay | <10ms | System audio stack |

**Total E2E Latency Formula:**
```
E2E_Latency = L1 + L2 + L3 + L4 + L5 + L6 + L7 + L8 + L9
Target: < 840ms (p50), < 1200ms (p95)
```

#### B. Barge-In Latency

| Metric ID | Component | Definition | Target |
|-----------|-----------|------------|--------|
| **B1** | Interruption Detection Time | Client VAD → local speech_start detection | <100ms |
| **B2** | Playback Stop Latency | speech_start → audio playback cancelled | <50ms |
| **B3** | Server Response Cancellation | Client cancel event → server stops TTS | <150ms |
| **B4** | Buffer Flush Time | Clear audio queue and reset state | <20ms |

**Total Barge-In Latency:**
```
Barge_In_Latency = B1 + B2 + B3 + B4
Target: < 320ms (p95)
```

---

### 3.2 Streaming Stability Metrics

| Metric | Definition | Formula | Target |
|--------|------------|---------|--------|
| **Audio Chunk Drop Rate** | % of audio chunks lost in transit | `(lost_chunks / total_chunks) × 100` | <0.1% |
| **Jitter** | Variance in packet arrival times | `σ(inter_arrival_time)` | <30ms |
| **WebSocket Reconnection Rate** | Reconnections per hour | `reconnects / uptime_hours` | <0.5/hr |
| **Audio Underrun Events** | PCM player buffer starvation count | `underrun_events / session_duration` | <1/min |
| **Stream Continuity Score** | % of conversation without playback gaps | `(total_time - gap_time) / total_time × 100` | >98% |
| **Network Quality Index (NQI)** | Composite score of latency + jitter + loss | `1 / (1 + 0.3×latency + 0.5×jitter + 2×loss_rate)` | >0.85 |

---

### 3.3 Throughput Metrics

| Metric | Definition | Measurement | Target |
|--------|------------|-------------|--------|
| **Concurrent Sessions** | Max simultaneous WebSocket connections | Active WSS count | 100+ |
| **Audio Throughput** | MB/s of audio data processed | `sum(chunk_sizes) / time` | 10 MB/s |
| **Request Rate** | API calls per second (token minting) | `/rt-token` endpoint QPS | 10 req/s |
| **Message Throughput** | WebSocket messages/second | WS events/s | 500 msg/s |
| **CPU Utilization** | Backend container CPU usage | Docker stats | <70% |
| **Memory Footprint** | Per-session memory consumption | `RSS / active_sessions` | <50 MB/session |

---

### 3.4 Quality Metrics

#### A. ASR Quality

| Metric | Definition | Formula | Target |
|--------|------------|---------|--------|
| **Word Error Rate (WER)** | Transcription accuracy | `(S + D + I) / N` <br> S=substitutions, D=deletions, I=insertions, N=reference words | <5% |
| **Character Error Rate (CER)** | Character-level accuracy | `(S_c + D_c + I_c) / N_c` | <3% |
| **Real-Time Factor (RTF)** | Processing speed vs real-time | `processing_time / audio_duration` | <0.5 |
| **Silence Detection Accuracy** | Correct VAD silence/speech classification | `TP / (TP + FP)` | >95% |
| **Transcription Latency** | Time to final transcription after speech end | `transcript.done - speech_stopped` | <500ms |

#### B. TTS Quality

| Metric | Definition | Measurement | Target |
|--------|------------|-------------|--------|
| **Mean Opinion Score (MOS)** | Subjective audio quality (1-5 scale) | Human evaluation | >4.0 |
| **Prosody Naturalness** | Intonation and rhythm quality | Acoustic feature analysis | >3.8 MOS |
| **Audio Fidelity** | Frequency response and distortion | PESQ/POLQA scores | >3.5 |
| **Voice Consistency** | Stable voice characteristics across utterances | Embedding distance | <0.15 |

#### C. Conversation Quality

| Metric | Definition | Measurement | Target |
|--------|------------|-------------|--------|
| **Response Relevance** | LLM answer appropriateness | BERT-score / human eval | >0.85 |
| **Context Retention** | Correct reference to prior conversation | Fact recall accuracy | >90% |
| **Hallucination Rate** | % responses with unverified claims | Automated fact-checking | <5% |
| **Turn-Taking Smoothness** | Natural conversation flow | Inter-turn gap analysis | 200-500ms |

---

### 3.5 Robustness Metrics

| Scenario | Metric | Definition | Target |
|----------|--------|------------|--------|
| **Network Degradation** | Graceful Degradation Score | Performance retention at 50% packet loss | >60% functionality |
| **High Load** | 95th Percentile Latency Under Load | E2E latency at 80% CPU | <2× baseline |
| **Error Recovery** | Automatic Recovery Rate | % of transient errors auto-recovered | >95% |
| **Failure Isolation** | Blast Radius | % services affected by single component failure | <30% |
| **Uptime** | Service Availability | `(uptime / total_time) × 100` | >99.5% |
| **MTTR** | Mean Time to Recovery | Average incident resolution time | <15 min |

---

## 4. Instrumentation Architecture

### 4.1 Client-Side Instrumentation (Browser)

**Performance Timing Events:**
```javascript
const performanceTracker = {
  // Latency tracking
  audioCapture: { start: null, end: null },
  encoding: { start: null, end: null },
  wsSend: { start: null, end: null },
  wsReceive: { start: null, end: null },
  audioRender: { start: null, end: null },

  // Streaming metrics
  chunksDropped: 0,
  jitterBuffer: [],
  underruns: 0,

  // Barge-in metrics
  interruptionTimes: [],
  playbackStopLatencies: [],

  // Session metrics
  sessionStart: Date.now(),
  messagesReceived: 0,
  messagesSent: 0,
  audioBytesSent: 0,
  audioBytesReceived: 0,

  // Quality metrics
  vadFalsePositives: 0,
  vadFalseNegatives: 0,
  transcriptionDelays: [],
}
```

**Instrumentation Points:**
1. `navigator.mediaDevices.getUserMedia()` - L1 baseline
2. ScriptProcessor `onaudioprocess` - L2 processing
3. `ws.send()` with timestamp - L3 network
4. `ws.onmessage` for all event types - L6, L7
5. PCM player `process()` - L8 rendering
6. AudioContext `currentTime` - L9 output

### 4.2 Server-Side Instrumentation (FastAPI)

**Prometheus Metrics Library:**
```python
from prometheus_client import Counter, Histogram, Gauge, Summary

# Latency histograms
token_mint_latency = Histogram(
    'token_mint_latency_seconds',
    'Token minting latency',
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0]
)

openai_api_latency = Histogram(
    'openai_api_latency_seconds',
    'OpenAI API call latency',
    ['endpoint']
)

# Throughput counters
websocket_connections = Gauge(
    'websocket_active_connections',
    'Number of active WebSocket connections'
)

api_requests_total = Counter(
    'api_requests_total',
    'Total API requests',
    ['method', 'endpoint', 'status']
)

# Error tracking
rate_limit_exceeded = Counter(
    'rate_limit_exceeded_total',
    'Rate limit violations',
    ['endpoint']
)

# Resource usage
memory_usage_bytes = Gauge(
    'memory_usage_bytes',
    'Process memory usage'
)
```

**Middleware Stack:**
```python
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start_time = time.perf_counter()

    response = await call_next(request)

    duration = time.perf_counter() - start_time
    api_requests_total.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()

    return response
```

### 4.3 Infrastructure Metrics (Docker + Traefik)

**Docker Stats Collection:**
- CPU percentage per container
- Memory usage (RSS, cache, swap)
- Network I/O (bytes in/out)
- Disk I/O (read/write ops)

**Traefik Metrics:**
- Request count by service
- Response time percentiles
- Active connections
- TLS handshake duration
- Retry attempts

---

## 5. Benchmarking Framework

### 5.1 Load Testing Suite

**Test Scenarios:**

| Test | Description | Parameters | Success Criteria |
|------|-------------|------------|------------------|
| **Baseline** | Single user, ideal conditions | 1 concurrent session | E2E latency <800ms |
| **Ramp-Up** | Gradual load increase | 1→100 sessions over 5 min | No >20% latency degradation |
| **Sustained Load** | Continuous high traffic | 50 concurrent, 30 min | p95 latency <1.5s |
| **Spike** | Sudden traffic burst | 0→80 in 10s | <5% error rate |
| **Soak** | Extended operation | 20 concurrent, 24 hrs | No memory leaks, uptime >99% |
| **Chaos** | Random failures | Random pod kills, network delays | Auto-recovery <30s |

**Load Generation Tools:**
- **Locust** for HTTP endpoint testing
- **Artillery** for WebSocket load testing
- **Custom Playwright** scripts for realistic browser simulation

### 5.2 Automated Test Suite

**File Structure:**
```
tests/
├── performance/
│   ├── test_latency.py          # E2E latency tests
│   ├── test_throughput.py       # Concurrent session tests
│   ├── test_streaming.py        # Stability tests
│   ├── test_barge_in.py         # Interruption tests
│   └── test_quality.py          # ASR/TTS quality tests
├── benchmarks/
│   ├── baseline_results.json    # Reference metrics
│   ├── load_scenarios.yml       # Test configurations
│   └── compare.py               # Result comparison tool
└── fixtures/
    ├── audio_samples/           # Test audio files
    ├── transcripts/             # Ground truth transcripts
    └── network_profiles/        # Simulated network conditions
```

**Example Test:**
```python
@pytest.mark.benchmark
async def test_end_to_end_latency(metrics_collector):
    """Measure E2E latency from mic to speaker."""

    # Setup
    client = VoiceAssistantClient()
    audio_file = "fixtures/audio_samples/hello_world.wav"

    # Execute
    start = time.perf_counter()
    await client.connect()
    await client.send_audio(audio_file)

    # Wait for response audio
    response = await client.receive_audio()
    end = time.perf_counter()

    # Validate
    latency = (end - start) * 1000  # ms
    assert latency < 1200, f"E2E latency {latency}ms exceeds threshold"

    metrics_collector.record("e2e_latency", latency)
```

### 5.3 Quality Evaluation Pipeline

**ASR Evaluation:**
```python
def evaluate_asr_accuracy(test_dataset):
    """
    Args:
        test_dataset: List of (audio_file, reference_transcript) tuples

    Returns:
        dict: WER, CER, latency metrics
    """
    from jiwer import wer, cer

    results = []
    for audio, reference in test_dataset:
        start = time.time()
        hypothesis = transcribe(audio)
        latency = time.time() - start

        results.append({
            'wer': wer(reference, hypothesis),
            'cer': cer(reference, hypothesis),
            'latency': latency,
            'rtf': latency / get_audio_duration(audio)
        })

    return aggregate_results(results)
```

**TTS Evaluation:**
```python
def evaluate_tts_quality(test_sentences):
    """
    Measure TTS quality using PESQ and MOS prediction.
    """
    from pesq import pesq
    from speechbrain.pretrained import MOS_PREDICTOR

    mos_model = MOS_PREDICTOR.from_hparams(source="speechbrain/mos-predictor")

    scores = []
    for text, reference_audio in test_sentences:
        synthesized = synthesize_speech(text)

        # Objective metric
        pesq_score = pesq(16000, reference_audio, synthesized, 'wb')

        # Predicted MOS
        mos = mos_model.predict(synthesized)

        scores.append({'text': text, 'pesq': pesq_score, 'mos': mos})

    return scores
```

---

## 6. Monitoring Dashboard Design

### 6.1 Real-Time Dashboard (Grafana)

**Panel Layout:**

```
┌────────────────────────────────────────────────────────────────┐
│                    System Health Overview                       │
│  [🟢 Uptime: 99.8%]  [⚡ Active Sessions: 23]  [🔥 CPU: 45%]  │
└────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────┬──────────────────────────────┐
│   E2E Latency Distribution      │   Barge-In Response Time     │
│   ┌─────────────────────────┐   │   ┌──────────────────────┐   │
│   │     [Heatmap Graph]     │   │   │  [Percentile Chart]  │   │
│   │  p50: 780ms  p95: 1120ms│   │   │  p50: 250ms p95: 380ms  │
│   └─────────────────────────┘   │   └──────────────────────┘   │
├─────────────────────────────────┼──────────────────────────────┤
│   Streaming Stability           │   Throughput Metrics         │
│   ┌─────────────────────────┐   │   ┌──────────────────────┐   │
│   │ Packet Loss: 0.02%      │   │   │ QPS: 8.5 req/s       │   │
│   │ Jitter: 12ms            │   │   │ Audio: 2.1 MB/s      │   │
│   │ Reconnects: 0.3/hr      │   │   │ Concurrency: 23      │   │
│   └─────────────────────────┘   │   └──────────────────────┘   │
├─────────────────────────────────┴──────────────────────────────┤
│   Quality Metrics                                              │
│   ┌────────────┬────────────┬────────────┬────────────┐        │
│   │  WER: 3.2% │ MOS: 4.1   │ Relevance  │ Context    │        │
│   │            │            │  89%       │  Retain 92%│        │
│   └────────────┴────────────┴────────────┴────────────┘        │
├────────────────────────────────────────────────────────────────┤
│   Resource Utilization                                         │
│   [CPU Timeline] [Memory Timeline] [Network I/O Timeline]      │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│   Recent Errors & Anomalies                                    │
│   • 2025-11-14 14:32:18 - Rate limit triggered (IP: 1.2.3.4)   │
│   • 2025-11-14 14:15:42 - WebSocket reconnect (SessionID: abc) │
└────────────────────────────────────────────────────────────────┘
```

### 6.2 Alert Configuration

**Critical Alerts (PagerDuty):**
- E2E latency p95 > 2000ms for 5 minutes
- Error rate > 5% for 2 minutes
- Service down (health check fails)
- CPU > 90% for 3 minutes
- Memory usage > 85%

**Warning Alerts (Slack):**
- E2E latency p95 > 1500ms for 10 minutes
- Barge-in latency > 500ms
- WebSocket reconnection rate > 1/hour
- Disk space > 80%
- TLS certificate expires in <7 days

---

## 7. Evaluation Methodology

### 7.1 Continuous Benchmarking

**Automated Daily Tests:**
1. **Morning Baseline** (3 AM UTC)
   - Run full benchmark suite
   - Compare against historical data
   - Generate trend report

2. **Peak Load Simulation** (2 PM UTC)
   - Simulate production-like traffic
   - Measure degradation under load

3. **Weekly Quality Audit** (Sunday)
   - ASR WER evaluation on test set
   - TTS MOS assessment
   - LLM response quality check

### 7.2 A/B Testing Framework

**Experiment Structure:**
```python
class ExperimentConfig:
    name: str
    variant_a: str  # Control
    variant_b: str  # Treatment
    traffic_split: float  # % to variant B
    metrics: List[str]
    duration_days: int

experiments = [
    ExperimentConfig(
        name="lower_tts_latency",
        variant_a="gpt-4o-mini-realtime",
        variant_b="gpt-4o-realtime",  # Hypothetical faster model
        traffic_split=0.1,
        metrics=["e2e_latency", "tts_quality_mos", "cost_per_session"],
        duration_days=7
    )
]
```

### 7.3 Research Paper Metrics

**For academic publication, report:**

1. **Latency Analysis:**
   - Mean, median, p95, p99 for all L1-L9 components
   - Breakdown by conversation stage (greeting, query, response)
   - Comparison to baseline systems (e.g., Google Duplex, Amazon Alexa)

2. **Quality Evaluation:**
   - ASR: WER on LibriSpeech, Common Voice datasets
   - TTS: MOS from 50+ human raters
   - Conversation: GPT-4 as judge for response quality

3. **Robustness Testing:**
   - Performance across network conditions (3G, 4G, WiFi, lossy)
   - Multi-accent ASR accuracy (US, UK, Indian, Australian English)
   - Background noise resilience (SNR: 20dB, 10dB, 5dB)

4. **Ablation Studies:**
   - Impact of VAD threshold on false positives
   - Effect of audio buffer size on latency vs stability
   - Barge-in aggressiveness tuning

---

## 8. Implementation Roadmap

### Phase 1: Instrumentation (Week 1-2)
- [ ] Add Prometheus metrics to FastAPI backend
- [ ] Implement client-side performance tracking
- [ ] Setup Prometheus + Grafana stack in Docker Compose
- [ ] Create initial dashboard

### Phase 2: Benchmarking (Week 3-4)
- [ ] Develop automated test suite
- [ ] Collect baseline metrics
- [ ] Implement load testing scenarios
- [ ] Setup CI integration for regression testing

### Phase 3: Quality Evaluation (Week 5-6)
- [ ] Curate ASR/TTS test datasets
- [ ] Implement quality metrics pipeline
- [ ] Run initial quality benchmarks
- [ ] Setup weekly quality audits

### Phase 4: Advanced Analytics (Week 7-8)
- [ ] Implement distributed tracing (Jaeger)
- [ ] Add anomaly detection
- [ ] Setup A/B testing framework
- [ ] Create executive reporting dashboard

---

## 9. Cost Estimation

### Infrastructure Costs

| Component | Specification | Monthly Cost |
|-----------|---------------|--------------|
| Prometheus TSDB | 30-day retention, 1GB data | $15 (managed) |
| Grafana Cloud | 3 users, 10k metrics | $49 |
| Load testing VMs | 4 vCPU, 16GB RAM, on-demand | $50 (10 hrs/month) |
| Log storage (ELK) | 50GB/month | $30 |
| **Total** | | **$144/month** |

### Development Effort

| Phase | Tasks | Estimated Hours |
|-------|-------|-----------------|
| Phase 1 | Instrumentation | 40 hours |
| Phase 2 | Benchmarking | 60 hours |
| Phase 3 | Quality Eval | 50 hours |
| Phase 4 | Advanced Analytics | 70 hours |
| **Total** | | **220 hours (~5.5 weeks)** |

---

## 10. References & Standards

### Academic Papers
1. **Latency Measurement:**
   - "Characterizing and Measuring the Performance of WebRTC" (IMC 2015)
   - "Low-Latency Streaming ASR with Temporal Convolutional Networks" (INTERSPEECH 2019)

2. **Quality Metrics:**
   - "PESQ: Perceptual Evaluation of Speech Quality" (ITU-T P.862)
   - "MOS-LQO: Mean Opinion Score for Listening Quality Objective" (ITU-T P.863)

3. **Benchmarking:**
   - "MLPerf Inference Benchmark" (arxiv.org/abs/1911.02549)
   - "Evaluating Conversational AI Systems" (Microsoft Research 2020)

### Industry Standards
- **ITU-T G.114:** One-way transmission time (latency budgets)
- **WebRTC Stats API:** W3C standard for media metrics
- **RED Method:** Rate, Errors, Duration for microservices
- **USE Method:** Utilization, Saturation, Errors for resource monitoring

---

## Appendix A: Glossary

- **TTFT:** Time To First Token (LLM latency metric)
- **RTF:** Real-Time Factor (processing_time / audio_duration)
- **WER:** Word Error Rate (ASR accuracy metric)
- **MOS:** Mean Opinion Score (subjective quality 1-5 scale)
- **PESQ:** Perceptual Evaluation of Speech Quality (objective audio quality)
- **VAD:** Voice Activity Detection (speech vs silence classification)
- **NQI:** Network Quality Index (composite network performance score)

---

**Document Version:** 1.0
**Last Updated:** 2025-11-14
**Next Review:** 2025-12-14
