/**
 * Performance Metrics Tracker for Full-Duplex Voice Assistant
 * Tracks end-to-end latency, streaming stability, barge-in speed, and quality metrics
 */

class PerformanceTracker {
  constructor(config = {}) {
    this.config = {
      enableLogging: config.enableLogging ?? true,
      sendToServer: config.sendToServer ?? false,
      serverEndpoint: config.serverEndpoint ?? '/api/metrics',
      aggregationInterval: config.aggregationInterval ?? 10000, // 10s
      ...config
    };

    this.reset();
    this.startAggregationTimer();
  }

  reset() {
    // === Latency Metrics ===
    this.latency = {
      // Component latencies (L1-L9)
      audioCapture: [],           // L1: Microphone capture
      audioProcessing: [],        // L2: VAD + encoding
      clientNetwork: [],          // L3: WebSocket send
      asrProcessing: [],          // L4: Speech-to-text
      llmProcessing: [],          // L5: LLM generation (TTFT)
      ttsProcessing: [],          // L6: Text-to-audio first chunk
      audioDownload: [],          // L7: Audio chunk network
      audioRendering: [],         // L8: Decode + resample
      speakerOutput: [],          // L9: Audio output latency

      // End-to-end measurements
      endToEnd: [],               // Total speech → audio response
      firstTokenTime: [],         // Time to first LLM token
      firstAudioTime: [],         // Time to first TTS audio

      // Barge-in specific
      bargeInDetection: [],       // B1: VAD detection
      playbackStop: [],           // B2: Audio stop latency
      serverCancel: [],           // B3: Server response cancel
      bufferFlush: [],            // B4: Clear audio queue
      totalBargeIn: []            // Total interruption latency
    };

    // === Streaming Stability Metrics ===
    this.streaming = {
      chunksDropped: 0,
      totalChunksSent: 0,
      totalChunksReceived: 0,
      jitterSamples: [],          // Inter-arrival time variance
      lastPacketTime: null,
      underrunEvents: 0,
      reconnectionCount: 0,
      audioGaps: [],              // Detected silence gaps
      continuousPlaybackTime: 0,
      totalPlaybackTime: 0
    };

    // === Throughput Metrics ===
    this.throughput = {
      audioBytesSent: 0,
      audioBytesReceived: 0,
      messagesSent: 0,
      messagesReceived: 0,
      sessionStartTime: Date.now(),
      lastActivityTime: Date.now()
    };

    // === Quality Metrics ===
    this.quality = {
      // VAD accuracy
      vadTruePositives: 0,
      vadFalsePositives: 0,
      vadTrueNegatives: 0,
      vadFalseNegatives: 0,

      // ASR metrics
      transcriptionDelays: [],
      partialTranscripts: 0,
      finalTranscripts: 0,

      // TTS metrics
      audioChunksReceived: 0,
      ttsGenerationIds: new Set(),

      // Conversation metrics
      userTurns: 0,
      assistantTurns: 0,
      interruptionCount: 0,
      turnGaps: []
    };

    // === Robustness Metrics ===
    this.errors = {
      networkErrors: 0,
      audioErrors: 0,
      wsErrors: 0,
      timeouts: 0,
      rateLimit429: 0,
      apiErrors: {}
    };

    // === Active Tracking State ===
    this.activeSpan = {
      speechStart: null,          // User started speaking
      speechEnd: null,            // User stopped speaking
      firstTranscript: null,      // First ASR delta
      finalTranscript: null,      // ASR done
      responseCreated: null,      // LLM response start
      firstTextDelta: null,       // First LLM token
      firstAudioDelta: null,      // First TTS audio
      firstAudioPlayed: null,     // Audio started playing
      responseComplete: null      // Conversation turn complete
    };

    // Network quality tracking
    this.networkQuality = {
      currentRTT: null,
      rttSamples: [],
      bandwidthSamples: []
    };
  }

  // ==================== Latency Tracking ====================

  /**
   * Mark the start of a user speech event
   */
  markSpeechStart() {
    this.activeSpan.speechStart = performance.now();
    this.quality.userTurns++;

    if (this.config.enableLogging) {
      console.log('[Metrics] Speech started');
    }
  }

  /**
   * Mark the end of user speech
   */
  markSpeechEnd() {
    this.activeSpan.speechEnd = performance.now();

    if (this.activeSpan.speechStart) {
      const duration = this.activeSpan.speechEnd - this.activeSpan.speechStart;
      if (this.config.enableLogging) {
        console.log(`[Metrics] Speech duration: ${duration.toFixed(2)}ms`);
      }
    }
  }

  /**
   * Track audio chunk send timing (L3: Client Network Latency)
   */
  trackAudioSend(chunkSize) {
    const timestamp = performance.now();
    this.throughput.audioBytesSent += chunkSize;
    this.throughput.messagesSent++;
    this.streaming.totalChunksSent++;
    this.throughput.lastActivityTime = Date.now();

    return timestamp; // Return for potential RTT calculation
  }

  /**
   * Track first ASR transcript received (L4: ASR Processing Latency)
   */
  trackFirstTranscript() {
    const now = performance.now();

    if (!this.activeSpan.firstTranscript && this.activeSpan.speechStart) {
      this.activeSpan.firstTranscript = now;
      const latency = now - this.activeSpan.speechStart;
      this.latency.asrProcessing.push(latency);

      if (this.config.enableLogging) {
        console.log(`[Metrics] ASR latency: ${latency.toFixed(2)}ms`);
      }
    }

    this.quality.partialTranscripts++;
  }

  /**
   * Track final ASR transcript
   */
  trackFinalTranscript() {
    const now = performance.now();

    if (this.activeSpan.speechEnd) {
      const delay = now - this.activeSpan.speechEnd;
      this.quality.transcriptionDelays.push(delay);
    }

    this.activeSpan.finalTranscript = now;
    this.quality.finalTranscripts++;
  }

  /**
   * Track response creation (L5: LLM Processing Latency - TTFT)
   */
  trackResponseCreated() {
    const now = performance.now();
    this.activeSpan.responseCreated = now;

    if (this.activeSpan.speechEnd) {
      const ttft = now - this.activeSpan.speechEnd;
      this.latency.firstTokenTime.push(ttft);

      if (this.config.enableLogging) {
        console.log(`[Metrics] Time to First Token: ${ttft.toFixed(2)}ms`);
      }
    }

    this.quality.assistantTurns++;
  }

  /**
   * Track first text delta from LLM
   */
  trackFirstTextDelta() {
    if (!this.activeSpan.firstTextDelta && this.activeSpan.responseCreated) {
      const now = performance.now();
      this.activeSpan.firstTextDelta = now;
      const latency = now - this.activeSpan.responseCreated;
      this.latency.llmProcessing.push(latency);
    }
  }

  /**
   * Track first audio delta received (L6: TTS Processing Latency)
   */
  trackFirstAudioDelta(generationId) {
    const now = performance.now();

    if (!this.activeSpan.firstAudioDelta && this.activeSpan.responseCreated) {
      this.activeSpan.firstAudioDelta = now;
      const latency = now - this.activeSpan.responseCreated;
      this.latency.ttsProcessing.push(latency);

      if (this.config.enableLogging) {
        console.log(`[Metrics] TTS latency: ${latency.toFixed(2)}ms`);
      }
    }

    this.quality.audioChunksReceived++;
    this.quality.ttsGenerationIds.add(generationId);
  }

  /**
   * Track audio chunk received (L7: Audio Download Latency)
   */
  trackAudioReceived(chunkSize, sendTime = null) {
    const now = performance.now();
    this.throughput.audioBytesReceived += chunkSize;
    this.throughput.messagesReceived++;
    this.streaming.totalChunksReceived++;

    // Calculate jitter if we have previous packet
    if (this.streaming.lastPacketTime) {
      const interArrivalTime = now - this.streaming.lastPacketTime;
      this.streaming.jitterSamples.push(interArrivalTime);
    }
    this.streaming.lastPacketTime = now;

    // Calculate network latency if send time provided
    if (sendTime) {
      const networkLatency = now - sendTime;
      this.latency.clientNetwork.push(networkLatency);
    }
  }

  /**
   * Track audio playback started (L8: Audio Rendering Latency)
   */
  trackAudioPlaybackStart() {
    const now = performance.now();

    if (!this.activeSpan.firstAudioPlayed && this.activeSpan.firstAudioDelta) {
      this.activeSpan.firstAudioPlayed = now;
      const latency = now - this.activeSpan.firstAudioDelta;
      this.latency.audioRendering.push(latency);
    }
  }

  /**
   * Track response complete and calculate end-to-end latency
   */
  trackResponseComplete() {
    const now = performance.now();
    this.activeSpan.responseComplete = now;

    // Calculate full end-to-end latency
    if (this.activeSpan.speechStart && this.activeSpan.firstAudioPlayed) {
      const e2eLatency = this.activeSpan.firstAudioPlayed - this.activeSpan.speechStart;
      this.latency.endToEnd.push(e2eLatency);

      if (this.config.enableLogging) {
        console.log(`[Metrics] End-to-End Latency: ${e2eLatency.toFixed(2)}ms`);
      }
    }

    // Calculate turn gap
    if (this.activeSpan.speechEnd && this.activeSpan.firstAudioPlayed) {
      const turnGap = this.activeSpan.firstAudioPlayed - this.activeSpan.speechEnd;
      this.quality.turnGaps.push(turnGap);
    }

    // Reset span for next turn
    this.resetActiveSpan();
  }

  resetActiveSpan() {
    this.activeSpan = {
      speechStart: null,
      speechEnd: null,
      firstTranscript: null,
      finalTranscript: null,
      responseCreated: null,
      firstTextDelta: null,
      firstAudioDelta: null,
      firstAudioPlayed: null,
      responseComplete: null
    };
  }

  // ==================== Barge-In Tracking ====================

  /**
   * Track barge-in/interruption event
   */
  trackBargeIn(stage, startTime) {
    const latency = performance.now() - startTime;

    switch (stage) {
      case 'detection':
        this.latency.bargeInDetection.push(latency);
        break;
      case 'playback_stop':
        this.latency.playbackStop.push(latency);
        break;
      case 'server_cancel':
        this.latency.serverCancel.push(latency);
        break;
      case 'buffer_flush':
        this.latency.bufferFlush.push(latency);
        break;
      case 'total':
        this.latency.totalBargeIn.push(latency);
        this.quality.interruptionCount++;
        if (this.config.enableLogging) {
          console.log(`[Metrics] Barge-in latency: ${latency.toFixed(2)}ms`);
        }
        break;
    }
  }

  // ==================== Streaming Stability ====================

  /**
   * Track audio underrun event (buffer starvation)
   */
  trackUnderrun() {
    this.streaming.underrunEvents++;
    if (this.config.enableLogging) {
      console.warn('[Metrics] Audio underrun detected');
    }
  }

  /**
   * Track WebSocket reconnection
   */
  trackReconnection() {
    this.streaming.reconnectionCount++;
    this.errors.networkErrors++;
    if (this.config.enableLogging) {
      console.warn('[Metrics] WebSocket reconnection');
    }
  }

  /**
   * Track audio gap/silence
   */
  trackAudioGap(duration) {
    this.streaming.audioGaps.push(duration);
  }

  // ==================== Quality Metrics ====================

  /**
   * Track VAD classification
   */
  trackVAD(prediction, groundTruth) {
    if (prediction && groundTruth) {
      this.quality.vadTruePositives++;
    } else if (prediction && !groundTruth) {
      this.quality.vadFalsePositives++;
    } else if (!prediction && !groundTruth) {
      this.quality.vadTrueNegatives++;
    } else {
      this.quality.vadFalseNegatives++;
    }
  }

  // ==================== Error Tracking ====================

  /**
   * Track error events
   */
  trackError(type, details = {}) {
    switch (type) {
      case 'network':
        this.errors.networkErrors++;
        break;
      case 'audio':
        this.errors.audioErrors++;
        break;
      case 'websocket':
        this.errors.wsErrors++;
        break;
      case 'timeout':
        this.errors.timeouts++;
        break;
      case 'rate_limit':
        this.errors.rateLimit429++;
        break;
      case 'api':
        const code = details.code || 'unknown';
        this.errors.apiErrors[code] = (this.errors.apiErrors[code] || 0) + 1;
        break;
    }

    if (this.config.enableLogging) {
      console.error(`[Metrics] Error tracked: ${type}`, details);
    }
  }

  // ==================== Network Quality ====================

  /**
   * Measure round-trip time using ping-pong
   */
  async measureRTT(wsSend, timeout = 5000) {
    const pingId = Math.random().toString(36).substr(2, 9);
    const startTime = performance.now();

    return new Promise((resolve) => {
      const timeoutId = setTimeout(() => {
        resolve(null);
      }, timeout);

      const handler = (event) => {
        if (event.data.type === 'pong' && event.data.ping_id === pingId) {
          clearTimeout(timeoutId);
          const rtt = performance.now() - startTime;
          this.networkQuality.currentRTT = rtt;
          this.networkQuality.rttSamples.push(rtt);
          resolve(rtt);
        }
      };

      // This would need integration with WebSocket message handler
      wsSend({ type: 'ping', ping_id: pingId });
    });
  }

  // ==================== Aggregation & Reporting ====================

  /**
   * Calculate percentiles for an array
   */
  percentile(arr, p) {
    if (arr.length === 0) return null;
    const sorted = [...arr].sort((a, b) => a - b);
    const index = Math.ceil((p / 100) * sorted.length) - 1;
    return sorted[Math.max(0, index)];
  }

  /**
   * Calculate standard deviation
   */
  std(arr) {
    if (arr.length === 0) return null;
    const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
    const variance = arr.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / arr.length;
    return Math.sqrt(variance);
  }

  /**
   * Calculate jitter (variance in inter-arrival times)
   */
  calculateJitter() {
    return this.std(this.streaming.jitterSamples);
  }

  /**
   * Calculate Network Quality Index
   */
  calculateNQI() {
    const avgLatency = this.networkQuality.rttSamples.length > 0
      ? this.networkQuality.rttSamples.reduce((a, b) => a + b, 0) / this.networkQuality.rttSamples.length
      : 0;
    const jitter = this.calculateJitter() || 0;
    const lossRate = this.streaming.totalChunksSent > 0
      ? this.streaming.chunksDropped / this.streaming.totalChunksSent
      : 0;

    const nqi = 1 / (1 + 0.3 * (avgLatency / 1000) + 0.5 * jitter + 2 * lossRate);
    return Math.max(0, Math.min(1, nqi)); // Clamp to [0, 1]
  }

  /**
   * Calculate VAD accuracy metrics
   */
  getVADMetrics() {
    const total = this.quality.vadTruePositives + this.quality.vadFalsePositives +
                  this.quality.vadTrueNegatives + this.quality.vadFalseNegatives;

    if (total === 0) return null;

    const accuracy = (this.quality.vadTruePositives + this.quality.vadTrueNegatives) / total;
    const precision = this.quality.vadTruePositives /
                      (this.quality.vadTruePositives + this.quality.vadFalsePositives) || 0;
    const recall = this.quality.vadTruePositives /
                   (this.quality.vadTruePositives + this.quality.vadFalseNegatives) || 0;
    const f1 = 2 * (precision * recall) / (precision + recall) || 0;

    return { accuracy, precision, recall, f1 };
  }

  /**
   * Generate comprehensive metrics report
   */
  generateReport() {
    const sessionDuration = (Date.now() - this.throughput.sessionStartTime) / 1000; // seconds

    return {
      timestamp: new Date().toISOString(),
      sessionDuration,

      // Latency metrics
      latency: {
        endToEnd: {
          count: this.latency.endToEnd.length,
          mean: this.latency.endToEnd.reduce((a, b) => a + b, 0) / this.latency.endToEnd.length || 0,
          p50: this.percentile(this.latency.endToEnd, 50),
          p95: this.percentile(this.latency.endToEnd, 95),
          p99: this.percentile(this.latency.endToEnd, 99)
        },
        asrProcessing: {
          mean: this.latency.asrProcessing.reduce((a, b) => a + b, 0) / this.latency.asrProcessing.length || 0,
          p95: this.percentile(this.latency.asrProcessing, 95)
        },
        llmTTFT: {
          mean: this.latency.firstTokenTime.reduce((a, b) => a + b, 0) / this.latency.firstTokenTime.length || 0,
          p95: this.percentile(this.latency.firstTokenTime, 95)
        },
        ttsProcessing: {
          mean: this.latency.ttsProcessing.reduce((a, b) => a + b, 0) / this.latency.ttsProcessing.length || 0,
          p95: this.percentile(this.latency.ttsProcessing, 95)
        },
        bargeIn: {
          count: this.latency.totalBargeIn.length,
          mean: this.latency.totalBargeIn.reduce((a, b) => a + b, 0) / this.latency.totalBargeIn.length || 0,
          p95: this.percentile(this.latency.totalBargeIn, 95)
        }
      },

      // Streaming stability
      streaming: {
        packetLossRate: this.streaming.totalChunksSent > 0
          ? (this.streaming.chunksDropped / this.streaming.totalChunksSent * 100).toFixed(3)
          : 0,
        jitterMs: this.calculateJitter()?.toFixed(2) || 0,
        underrunEvents: this.streaming.underrunEvents,
        reconnections: this.streaming.reconnectionCount,
        reconnectionsPerHour: (this.streaming.reconnectionCount / (sessionDuration / 3600)).toFixed(2),
        nqi: this.calculateNQI().toFixed(3)
      },

      // Throughput
      throughput: {
        audioSentMBps: (this.throughput.audioBytesSent / sessionDuration / 1024 / 1024).toFixed(3),
        audioReceivedMBps: (this.throughput.audioBytesReceived / sessionDuration / 1024 / 1024).toFixed(3),
        messagesPerSecond: (this.throughput.messagesReceived / sessionDuration).toFixed(2),
        totalMessagesSent: this.throughput.messagesSent,
        totalMessagesReceived: this.throughput.messagesReceived
      },

      // Quality
      quality: {
        userTurns: this.quality.userTurns,
        assistantTurns: this.quality.assistantTurns,
        interruptions: this.quality.interruptionCount,
        avgTurnGapMs: this.quality.turnGaps.length > 0
          ? (this.quality.turnGaps.reduce((a, b) => a + b, 0) / this.quality.turnGaps.length).toFixed(2)
          : 0,
        transcriptionDelayMs: this.quality.transcriptionDelays.length > 0
          ? (this.quality.transcriptionDelays.reduce((a, b) => a + b, 0) / this.quality.transcriptionDelays.length).toFixed(2)
          : 0,
        vad: this.getVADMetrics()
      },

      // Errors
      errors: {
        network: this.errors.networkErrors,
        audio: this.errors.audioErrors,
        websocket: this.errors.wsErrors,
        timeouts: this.errors.timeouts,
        rateLimit: this.errors.rateLimit429,
        api: this.errors.apiErrors
      },

      // Network quality
      network: {
        currentRTT: this.networkQuality.currentRTT?.toFixed(2),
        avgRTT: this.networkQuality.rttSamples.length > 0
          ? (this.networkQuality.rttSamples.reduce((a, b) => a + b, 0) / this.networkQuality.rttSamples.length).toFixed(2)
          : null
      }
    };
  }

  /**
   * Start periodic aggregation and reporting
   */
  startAggregationTimer() {
    this.aggregationTimer = setInterval(() => {
      const report = this.generateReport();

      if (this.config.enableLogging) {
        console.log('[Metrics] Periodic Report:', report);
      }

      if (this.config.sendToServer) {
        this.sendMetricsToServer(report);
      }

      // Emit custom event for dashboard consumption
      window.dispatchEvent(new CustomEvent('metrics-report', { detail: report }));

    }, this.config.aggregationInterval);
  }

  /**
   * Send metrics to backend API
   */
  async sendMetricsToServer(report) {
    try {
      await fetch(this.config.serverEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(report)
      });
    } catch (error) {
      console.error('[Metrics] Failed to send to server:', error);
    }
  }

  /**
   * Get current metrics snapshot
   */
  getSnapshot() {
    return this.generateReport();
  }

  /**
   * Export metrics as JSON for download
   */
  exportMetrics() {
    const report = this.generateReport();
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `metrics-${new Date().toISOString()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  /**
   * Cleanup and stop tracking
   */
  destroy() {
    if (this.aggregationTimer) {
      clearInterval(this.aggregationTimer);
    }
  }
}

// Export for use in script.js
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PerformanceTracker;
}
