# E2E Latency Measurement Integration Guide

## Overview
This guide explains how to integrate latency tracking into your existing full-duplex speech system to measure end-to-end performance.

## Step 1: Import the Latency Tracker

Add to the top of `web/script.js`:

```javascript
import { LatencyTracker } from './latency_tracker.js';

// Initialize global tracker
const latencyTracker = new LatencyTracker();
```

## Step 2: Track Speech Start

When server VAD emits `speech_started` event (already exists around line 878):

```javascript
// In your WebSocket message handler
if (t === "input_audio_buffer.speech_started") {
  // Existing code to stop assistant audio
  if (pcmPlayer) pcmPlayer.stopAll();

  // ADD THIS: Track speech start time
  latencyTracker.onSpeechStart();
  return;
}
```

## Step 3: Track Speech Stop Event

When server VAD emits `speech_stopped` (around line 862):

```javascript
if (t === "transcription.speech_stopped" || t === "input_audio_buffer.collected") {
  // ADD THIS: Track when VAD detected speech end
  latencyTracker.onSpeechStopEvent();

  // Existing code
  ws.send(JSON.stringify({
    type: "response.create",
    response: { /* ... */ }
  }));
  return;
}
```

## Step 4: Track Transcript Complete

When ASR transcript is finalized (around line 882):

```javascript
if (t === "transcription.completed" || t === "input_audio_buffer.transcription.completed") {
  const transcript = msg.transcript || "";

  // ADD THIS: Track transcript completion
  latencyTracker.onTranscriptComplete(transcript);

  // Existing code to display transcript
  // ...
  return;
}
```

## Step 5: Track First LLM Token

When response generation starts (look for `response.created` or first `response.delta`):

```javascript
// Track first response event (around response handling)
if (t === "response.created" || t === "response.output_item.added") {
  // ADD THIS: Track first LLM response
  latencyTracker.onFirstToken();
  return;
}
```

## Step 6: Track First Audio Chunk

When first TTS audio arrives (around line 899):

```javascript
if (t === "response.output_audio.delta" || t === "response.audio.delta") {
  const b64 = msg.delta || msg.audio;

  // ADD THIS: Track first audio chunk (only once per turn)
  if (!latencyTracker.currentTurn.firstAudioChunkTime && b64) {
    latencyTracker.onFirstAudioChunk();
  }

  // Existing code
  if (b64 && pcmPlayer) pcmPlayer.enqueueBase64PCM16(b64, activeGen);
  return;
}
```

## Step 7: Track Audio Playback Start

Modify your PCM player to notify when audio actually starts playing. In your PCM player class:

```javascript
class PCMPlayer {
  constructor() {
    // ... existing code ...
    this.hasPlayedInCurrentTurn = false;
  }

  enqueueBase64PCM16(b64, generation) {
    // ... existing decoding logic ...

    // When first chunk for this turn starts playing
    if (!this.hasPlayedInCurrentTurn) {
      this.hasPlayedInCurrentTurn = true;

      // ADD THIS: Notify latency tracker
      window.latencyTracker.onAudioPlaybackStart();
    }

    // ... rest of existing code ...
  }

  stopAll() {
    // ... existing stop logic ...

    // Reset flag for next turn
    this.hasPlayedInCurrentTurn = false;
  }
}
```

## Step 8: Track Barge-In Latency

When user interrupts (around line 878):

```javascript
if (t === "input_audio_buffer.speech_started") {
  // ADD THIS: Track interrupt time
  latencyTracker.onUserInterrupt();

  // Existing code
  if (pcmPlayer) {
    pcmPlayer.stopAll();

    // ADD THIS: Track when audio actually stopped
    setTimeout(() => latencyTracker.onAudioStopped(), 10);
  }
  return;
}
```

## Step 9: Display Real-Time Statistics

Add UI element to display stats. In `index.html`:

```html
<!-- Add somewhere visible in your UI -->
<div id="latency-stats" style="position: fixed; top: 10px; right: 10px;
     background: rgba(0,0,0,0.8); color: #0f0; padding: 10px;
     font-family: monospace; font-size: 12px; max-width: 300px;
     display: none;">
</div>

<!-- Add button to toggle stats display -->
<button id="toggle-latency-stats" style="position: fixed; top: 10px; right: 320px;">
  Show Stats
</button>
```

Add JavaScript to toggle and update display:

```javascript
const statsBtn = document.getElementById('toggle-latency-stats');
const statsDiv = document.getElementById('latency-stats');

statsBtn?.addEventListener('click', () => {
  const isVisible = statsDiv.style.display === 'block';
  statsDiv.style.display = isVisible ? 'none' : 'block';
  statsBtn.textContent = isVisible ? 'Show Stats' : 'Hide Stats';

  if (!isVisible) {
    // Update stats every 2 seconds when visible
    const updateInterval = setInterval(() => {
      if (statsDiv.style.display !== 'block') {
        clearInterval(updateInterval);
        return;
      }
      latencyTracker.displayStats('latency-stats');
    }, 2000);

    // Initial display
    latencyTracker.displayStats('latency-stats');
  }
});
```

## Step 10: Export Measurements

Add button to download CSV of all measurements:

```javascript
// Add button in HTML
<button id="download-latency-csv">Download Latency Data</button>

// Add handler
document.getElementById('download-latency-csv')?.addEventListener('click', () => {
  latencyTracker.downloadCSV();
});
```

## Step 11: Backend API Endpoint (Optional)

To collect aggregate statistics, add endpoint in `src/assistant/main.py`:

```python
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Optional
import time

router = APIRouter()

class LatencyMetric(BaseModel):
    type: str  # 'e2e_latency' or 'barge_in_latency'
    total_ms: Optional[float] = None
    latency_ms: Optional[float] = None
    breakdown: Optional[Dict[str, float]] = None
    timestamp: int

# In-memory storage (use Redis/Postgres for production)
latency_metrics = []

@router.post("/api/metrics/latency")
async def record_latency(metric: LatencyMetric):
    """Receive client-side latency measurements"""
    latency_metrics.append({
        **metric.dict(),
        'server_timestamp': int(time.time() * 1000)
    })

    # Keep only last 10,000 measurements
    if len(latency_metrics) > 10_000:
        latency_metrics.pop(0)

    return {"status": "recorded"}

@router.get("/api/metrics/latency/stats")
async def get_latency_stats():
    """Get aggregate statistics"""
    if not latency_metrics:
        return {"error": "No data"}

    e2e_latencies = [m['total_ms'] for m in latency_metrics if m.get('total_ms')]
    barge_in_latencies = [m['latency_ms'] for m in latency_metrics if m.get('latency_ms')]

    def calc_stats(values):
        if not values:
            return None
        sorted_vals = sorted(values)
        return {
            'count': len(values),
            'mean': sum(values) / len(values),
            'median': sorted_vals[len(sorted_vals) // 2],
            'p50': sorted_vals[int(len(sorted_vals) * 0.50)],
            'p95': sorted_vals[int(len(sorted_vals) * 0.95)],
            'p99': sorted_vals[int(len(sorted_vals) * 0.99)],
            'min': sorted_vals[0],
            'max': sorted_vals[-1]
        }

    return {
        'e2e_latency': calc_stats(e2e_latencies),
        'barge_in_latency': calc_stats(barge_in_latencies),
        'total_measurements': len(latency_metrics)
    }

# Register router in main.py
app.include_router(router)
```

## Step 12: Prometheus Integration

Export metrics to Prometheus for long-term monitoring:

```python
from prometheus_client import Histogram

# Add to existing Prometheus metrics
E2E_LATENCY = Histogram(
    'e2e_latency_seconds',
    'End-to-end latency from speech to audio playback',
    buckets=[0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 10.0]
)

BARGE_IN_LATENCY = Histogram(
    'barge_in_latency_seconds',
    'Barge-in response latency',
    buckets=[0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 2.0]
)

@router.post("/api/metrics/latency")
async def record_latency(metric: LatencyMetric):
    # Record to Prometheus
    if metric.type == 'e2e_latency' and metric.total_ms:
        E2E_LATENCY.observe(metric.total_ms / 1000)
    elif metric.type == 'barge_in_latency' and metric.latency_ms:
        BARGE_IN_LATENCY.observe(metric.latency_ms / 1000)

    # ... rest of existing code
```

## Example Console Output

When properly integrated, you'll see console logs like:

```
[Latency] Speech started at 12345.6
[Latency] VAD detection: 823.4ms
[Latency] Transcript: "What's the weather like today?"
[Latency] ASR processing: 287.3ms
[Latency] LLM TTFT: 412.8ms
[Latency] TTS generation: 298.5ms
[Latency] Playback buffer: 67.2ms
[Latency] ⭐ E2E TOTAL: 1889.2ms
[Latency] Breakdown:
  VAD:      823.4ms (43.6%)
  ASR:      287.3ms (15.2%)
  LLM:      412.8ms (21.9%)
  TTS:      298.5ms (15.8%)
  Playback: 67.2ms (3.6%)
```

## Verification

To verify measurements are accurate:

1. **Check timestamps are sequential**: Each timestamp should be greater than the previous
2. **VAD latency should be ~800ms**: Matches your configured VAD window
3. **Total should sum correctly**: E2E = VAD + ASR + LLM + TTS + Playback
4. **Barge-in < 500ms**: Should meet your p95 target

## Troubleshooting

**Problem**: All timestamps are `null`
- **Solution**: Ensure `latencyTracker` is imported and initialized before use

**Problem**: E2E latency is too low (<1000ms)
- **Solution**: Check that speech_start is being called at the right time (when user starts speaking, not when VAD detects)

**Problem**: Missing measurements
- **Solution**: Check browser console for errors; ensure all event handlers are properly integrated

**Problem**: Timestamps out of order
- **Solution**: Use `performance.now()` instead of `Date.now()` for sub-millisecond precision

## Next Steps

1. Collect measurements from N=20 participants during user study
2. Export CSV after each session
3. Analyze statistics using Python/R
4. Compare against theoretical 1.4-2.0s estimate
5. Update paper with empirical E2E latency results!
