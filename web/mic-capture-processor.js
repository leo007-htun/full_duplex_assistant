// Emits fixed-size Float32 frames at downsampleTo Hz.
// Example: 48k -> 16k, 20ms -> 320 samples per post.
class MicCaptureProcessorV2 extends AudioWorkletProcessor {
  constructor({ processorOptions = {} } = {}) {
    super();

    // ---- config (with guards) ----
    const cfgRate = Number(processorOptions.downsampleTo) || 16000;
    const cfgMs   = Number(processorOptions.postIntervalMs) || 20;

    this.outRate  = Math.max(1, Math.floor(cfgRate));
    this.frameMs  = Math.max(1, Math.floor(cfgMs));
    this.frameLen = Math.max(1, Math.floor(this.outRate * this.frameMs / 1000)); // e.g., 320 @ 16k/20ms

    // Integer decimation if possible (e.g., 48000 -> 16000 uses /3)
    this.decim = Math.max(1, Math.round(sampleRate / this.outRate));
    this.integerDecim = Math.abs(sampleRate - this.outRate * this.decim) < 1e-6;
    this.phase = 0; // decimation counter

    // Linear-resampler state (for 44.1k→16k etc.)
    this.accum = 0;    // "outRate" ticks accumulated per input sample
    this.prev  = 0;    // previous input sample

    // Output buffer we fill and carve into fixed frames
    this.buf = new Float32Array(this.frameLen * 4);
    this.bufLen = 0;

    this.port.postMessage({
      type: 'debug',
      in_rate: sampleRate,
      rate: this.outRate,
      frame_len: this.frameLen
    });
  }

  _ensureCapacity(n) {
    if (this.bufLen + n <= this.buf.length) return;
    const next = new Float32Array(Math.max(this.buf.length * 2, this.bufLen + n));
    next.set(this.buf.subarray(0, this.bufLen));
    this.buf = next;
  }

  _pushSample(v) {
    this._ensureCapacity(1);
    this.buf[this.bufLen++] = v;
  }

  _postFramesIfReady() {
    while (this.bufLen >= this.frameLen) {
      const chunk = new Float32Array(this.frameLen);
      chunk.set(this.buf.subarray(0, this.frameLen));
      this.buf.copyWithin(0, this.frameLen, this.bufLen);
      this.bufLen -= this.frameLen;

      this.port.postMessage(
        { type: 'audio', samples: chunk, rate: this.outRate, frame_len: this.frameLen },
        [chunk.buffer]
      );
    }
  }

  process(inputs) {
    const input = inputs && inputs[0];
    if (!input || input.length === 0) return true;

    let ch = input[0];
    if (!ch || ch.length === 0) return true;

    // If more than one channel, quick mono average into L
    if (input.length > 1) {
      const L = input[0], R = input[1];
      const N = Math.min(L.length, R ? R.length : 0);
      if (N > 0) {
        for (let i = 0; i < N; i++) L[i] = 0.5 * (L[i] + (R ? R[i] : 0));
        ch = L;
      }
    }

    if (this.integerDecim && this.decim >= 1) {
      // Exact decimation path (e.g., 48k -> 16k by 3)
      for (let i = 0; i < ch.length; i++) {
        if (this.phase === 0) this._pushSample(ch[i]);
        this.phase++;
        if (this.phase >= this.decim) this.phase = 0; // prevent overflow
      }
    } else {
      // Generic linear resampler (44.1k -> 16k, etc.)
      const inRate  = sampleRate;
      const outRate = this.outRate;
      let prev = this.prev;

      for (let i = 0; i < ch.length; i++) {
        const curr = ch[i];
        this.accum += outRate;

        while (this.accum >= inRate) {
          const frac = (this.accum - inRate) / outRate; // in [0, 1)
          const y = prev + (curr - prev) * frac;
          this._pushSample(y);
          this.accum -= inRate;
        }
        prev = curr;
      }
      this.prev = prev;
    }

    this._postFramesIfReady();
    return true;
  }
}

registerProcessor('mic-capture-v2', MicCaptureProcessorV2);
