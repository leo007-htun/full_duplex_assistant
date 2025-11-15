/**
 * End-to-End Latency Measurement Module
 * Tracks latency from user speech to assistant audio playback
 *
 * IMPORTANT: E2E includes the full network round-trip:
 *
 * Browser ←──────────── WebSocket ─────────────→ OpenAI Realtime API
 *    |                                                    |
 *    └─ onSpeechStart() (user speaks)                   |
 *         ↓ (audio upload)                              ↓
 *         ────────────────────────────────────→ Server VAD + ASR Processing
 *                                                        ↓
 *    ←── onSpeechStopEvent() ──────────────── speech_stopped event
 *    ←── onTranscriptComplete() ──────────── (implicit - ASR done in VAD)
 *                                                        ↓
 *    ←── onFirstToken() ──────────────────── response.created (LLM starts)
 *                                                        ↓
 *    ←── onFirstAudioChunk() ─────────────── TTS Synthesis (audio.delta)
 *         ↓
 *    └─ onAudioPlaybackStart() (user hears assistant)
 *
 * NOTE: With server_vad, user transcription events are NOT sent by the API.
 * ASR latency is implicit in the VAD processing. We measure:
 * - VAD latency: speech_start → speech_stopped
 * - ASR latency: ~0ms (implicit in speech_stopped event)
 * - LLM latency: speech_stopped → response.created
 * - TTS latency: response.created → first audio.delta
 * - Playback: first audio.delta → browser playback
 *
 * All network latency (browser ↔ OpenAI) is automatically included because
 * we measure wall-clock time (performance.now()) between events.
 */

export class LatencyTracker {
  constructor() {
    // Latency measurement state
    this.measurements = {
      e2e_latency: [],           // Total: speech_start → audio_start
      vad_latency: [],           // speech_start → speech_stopped event
      asr_latency: [],           // speech_stopped → transcript_completed
      llm_latency: [],           // transcript_completed → first_token
      tts_latency: [],           // first_token → first_audio_chunk
      playback_latency: [],      // first_audio_chunk → actual_playback
      barge_in_latency: []       // user_interrupt → audio_stopped
    };

    // Current turn tracking
    this.currentTurn = {
      speechStartTime: null,
      speechStopEventTime: null,
      transcriptCompleteTime: null,
      firstTokenTime: null,
      firstAudioChunkTime: null,
      firstPlaybackTime: null,
      interruptTime: null,
      audioStopTime: null
    };

    // Configuration
    this.enabled = true;
    this.logToConsole = true;
    this.sendToBackend = true;
    this.backendUrl = '/api/metrics/latency';
  }

  /**
   * Mark the start of user speech
   * Called when VAD detects speech onset (client-side or server-side)
   */
  onSpeechStart() {
    if (!this.enabled) return;

    this.currentTurn.speechStartTime = performance.now();

    if (this.logToConsole) {
      console.log('[Latency] Speech started at', this.currentTurn.speechStartTime);
    }
  }

  /**
   * Mark when server VAD emits speech_stopped event
   */
  onSpeechStopEvent() {
    if (!this.enabled || !this.currentTurn.speechStartTime) return;

    this.currentTurn.speechStopEventTime = performance.now();

    const vadLatency = this.currentTurn.speechStopEventTime - this.currentTurn.speechStartTime;
    this.measurements.vad_latency.push(vadLatency);

    if (this.logToConsole) {
      console.log(`[Latency] VAD detection: ${vadLatency.toFixed(1)}ms`);
    }
  }

  /**
   * Mark when ASR transcript is finalized
   */
  onTranscriptComplete(transcript) {
    if (!this.enabled || !this.currentTurn.speechStopEventTime) return;

    this.currentTurn.transcriptCompleteTime = performance.now();

    const asrLatency = this.currentTurn.transcriptCompleteTime - this.currentTurn.speechStopEventTime;
    this.measurements.asr_latency.push(asrLatency);

    if (this.logToConsole) {
      console.log(`[Latency] ASR processing: ${asrLatency.toFixed(1)}ms`);
      console.log(`[Latency] Transcript: "${transcript}"`);
    }
  }

  /**
   * Mark when first LLM token arrives (or response.created event)
   */
  onFirstToken() {
    if (!this.enabled || !this.currentTurn.transcriptCompleteTime) return;

    this.currentTurn.firstTokenTime = performance.now();

    const llmLatency = this.currentTurn.firstTokenTime - this.currentTurn.transcriptCompleteTime;
    this.measurements.llm_latency.push(llmLatency);

    if (this.logToConsole) {
      console.log(`[Latency] LLM TTFT: ${llmLatency.toFixed(1)}ms`);
    }
  }

  /**
   * Mark when first TTS audio chunk arrives
   */
  onFirstAudioChunk() {
    if (!this.enabled || !this.currentTurn.firstTokenTime) return;

    this.currentTurn.firstAudioChunkTime = performance.now();

    const ttsLatency = this.currentTurn.firstAudioChunkTime - this.currentTurn.firstTokenTime;
    this.measurements.tts_latency.push(ttsLatency);

    if (this.logToConsole) {
      console.log(`[Latency] TTS generation: ${ttsLatency.toFixed(1)}ms`);
    }
  }

  /**
   * Mark when audio actually starts playing (browser AudioContext)
   */
  onAudioPlaybackStart() {
    if (!this.enabled || !this.currentTurn.firstAudioChunkTime) return;

    this.currentTurn.firstPlaybackTime = performance.now();

    const playbackLatency = this.currentTurn.firstPlaybackTime - this.currentTurn.firstAudioChunkTime;
    this.measurements.playback_latency.push(playbackLatency);

    // Calculate total E2E latency
    if (this.currentTurn.speechStartTime) {
      const e2eLatency = this.currentTurn.firstPlaybackTime - this.currentTurn.speechStartTime;
      this.measurements.e2e_latency.push(e2eLatency);

      if (this.logToConsole) {
        console.log(`[Latency] Playback buffer: ${playbackLatency.toFixed(1)}ms`);
        console.log(`[Latency] ⭐ E2E TOTAL: ${e2eLatency.toFixed(1)}ms`);
        this.logBreakdown();
      }

      // Send to backend for aggregation
      if (this.sendToBackend) {
        this.reportToBackend({
          type: 'e2e_latency',
          total_ms: e2eLatency,
          breakdown: {
            vad_ms: this.currentTurn.speechStopEventTime - this.currentTurn.speechStartTime,
            asr_ms: this.currentTurn.transcriptCompleteTime - this.currentTurn.speechStopEventTime,
            llm_ms: this.currentTurn.firstTokenTime - this.currentTurn.transcriptCompleteTime,
            tts_ms: this.currentTurn.firstAudioChunkTime - this.currentTurn.firstTokenTime,
            playback_ms: playbackLatency
          },
          timestamp: Date.now()
        });
      }
    }

    // Reset for next turn
    this.resetTurn();
  }

  /**
   * Mark when user interrupts (barge-in)
   */
  onUserInterrupt() {
    if (!this.enabled) return;

    this.currentTurn.interruptTime = performance.now();

    if (this.logToConsole) {
      console.log('[Latency] User interrupted at', this.currentTurn.interruptTime);
    }
  }

  /**
   * Mark when assistant audio actually stops after interrupt
   */
  onAudioStopped() {
    if (!this.enabled || !this.currentTurn.interruptTime) return;

    this.currentTurn.audioStopTime = performance.now();

    const bargeInLatency = this.currentTurn.audioStopTime - this.currentTurn.interruptTime;
    this.measurements.barge_in_latency.push(bargeInLatency);

    if (this.logToConsole) {
      console.log(`[Latency] Barge-in response: ${bargeInLatency.toFixed(1)}ms`);
    }

    if (this.sendToBackend) {
      this.reportToBackend({
        type: 'barge_in_latency',
        latency_ms: bargeInLatency,
        timestamp: Date.now()
      });
    }
  }

  /**
   * Reset current turn measurements
   */
  resetTurn() {
    this.currentTurn = {
      speechStartTime: null,
      speechStopEventTime: null,
      transcriptCompleteTime: null,
      firstTokenTime: null,
      firstAudioChunkTime: null,
      firstPlaybackTime: null,
      interruptTime: null,
      audioStopTime: null
    };
  }

  /**
   * Log breakdown of current turn
   */
  logBreakdown() {
    if (!this.currentTurn.speechStartTime || !this.currentTurn.firstPlaybackTime) return;

    const total = this.currentTurn.firstPlaybackTime - this.currentTurn.speechStartTime;

    console.log('[Latency] Breakdown:');
    if (this.currentTurn.speechStopEventTime) {
      const vad = this.currentTurn.speechStopEventTime - this.currentTurn.speechStartTime;
      const vadPct = ((vad / total) * 100).toFixed(1);
      console.log(`  VAD:      ${vad.toFixed(1)}ms (${vadPct}%)`);
    }
    if (this.currentTurn.transcriptCompleteTime) {
      const asr = this.currentTurn.transcriptCompleteTime - this.currentTurn.speechStopEventTime;
      const asrPct = ((asr / total) * 100).toFixed(1);
      console.log(`  ASR:      ${asr.toFixed(1)}ms (${asrPct}%)`);
    }
    if (this.currentTurn.firstTokenTime) {
      const llm = this.currentTurn.firstTokenTime - this.currentTurn.transcriptCompleteTime;
      const llmPct = ((llm / total) * 100).toFixed(1);
      console.log(`  LLM:      ${llm.toFixed(1)}ms (${llmPct}%)`);
    }
    if (this.currentTurn.firstAudioChunkTime) {
      const tts = this.currentTurn.firstAudioChunkTime - this.currentTurn.firstTokenTime;
      const ttsPct = ((tts / total) * 100).toFixed(1);
      console.log(`  TTS:      ${tts.toFixed(1)}ms (${ttsPct}%)`);
    }
    if (this.currentTurn.firstPlaybackTime) {
      const playback = this.currentTurn.firstPlaybackTime - this.currentTurn.firstAudioChunkTime;
      const playbackPct = ((playback / total) * 100).toFixed(1);
      console.log(`  Playback: ${playback.toFixed(1)}ms (${playbackPct}%)`);
    }
  }

  /**
   * Get statistics for a metric
   */
  getStats(metric) {
    const values = this.measurements[metric];
    if (!values || values.length === 0) {
      return null;
    }

    const sorted = [...values].sort((a, b) => a - b);
    const sum = sorted.reduce((a, b) => a + b, 0);
    const mean = sum / sorted.length;

    const variance = sorted.reduce((acc, val) => acc + Math.pow(val - mean, 2), 0) / sorted.length;
    const stddev = Math.sqrt(variance);

    return {
      count: sorted.length,
      min: sorted[0],
      max: sorted[sorted.length - 1],
      mean: mean,
      median: sorted[Math.floor(sorted.length / 2)],
      p50: sorted[Math.floor(sorted.length * 0.50)],
      p95: sorted[Math.floor(sorted.length * 0.95)],
      p99: sorted[Math.floor(sorted.length * 0.99)],
      stddev: stddev
    };
  }

  /**
   * Get all statistics
   */
  getAllStats() {
    const stats = {};
    for (const metric in this.measurements) {
      stats[metric] = this.getStats(metric);
    }
    return stats;
  }

  /**
   * Export measurements as CSV
   */
  exportCSV() {
    const lines = ['metric,value_ms,timestamp'];

    for (const [metric, values] of Object.entries(this.measurements)) {
      values.forEach((value, idx) => {
        lines.push(`${metric},${value.toFixed(2)},${Date.now() - (values.length - idx) * 1000}`);
      });
    }

    return lines.join('\n');
  }

  /**
   * Download measurements as CSV file
   */
  downloadCSV() {
    const csv = this.exportCSV();
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `latency_measurements_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Send measurement to backend
   */
  async reportToBackend(data) {
    try {
      await fetch(this.backendUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
    } catch (err) {
      console.warn('[Latency] Failed to report to backend:', err);
    }
  }

  /**
   * Display live statistics in UI
   */
  displayStats(containerId = 'latency-stats') {
    const container = document.getElementById(containerId);
    if (!container) return;

    const stats = this.getAllStats();
    let html = '<h3>Latency Statistics</h3>';

    for (const [metric, data] of Object.entries(stats)) {
      if (!data) continue;

      html += `<div class="metric-stats">
        <h4>${metric.replace(/_/g, ' ').toUpperCase()}</h4>
        <table>
          <tr><td>Count:</td><td>${data.count}</td></tr>
          <tr><td>Mean:</td><td>${data.mean.toFixed(1)}ms</td></tr>
          <tr><td>Median:</td><td>${data.median.toFixed(1)}ms</td></tr>
          <tr><td>P95:</td><td>${data.p95.toFixed(1)}ms</td></tr>
          <tr><td>P99:</td><td>${data.p99.toFixed(1)}ms</td></tr>
          <tr><td>Min:</td><td>${data.min.toFixed(1)}ms</td></tr>
          <tr><td>Max:</td><td>${data.max.toFixed(1)}ms</td></tr>
          <tr><td>StdDev:</td><td>${data.stddev.toFixed(1)}ms</td></tr>
        </table>
      </div>`;
    }

    container.innerHTML = html;
  }

  /**
   * Clear all measurements
   */
  clear() {
    for (const metric in this.measurements) {
      this.measurements[metric] = [];
    }
    this.resetTurn();
  }
}

// Create global instance
window.latencyTracker = new LatencyTracker();

export default LatencyTracker;
