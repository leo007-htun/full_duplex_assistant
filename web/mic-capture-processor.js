// Emits fixed-size Float32 frames at downsampleTo Hz.
// Example: 48k -> 16k, 20ms -> 320 samples per post.
class MicCaptureProcessorV2 extends AudioWorkletProcessor {
  constructor({ processorOptions = {} } = {}) {
    super();
    this.outRate  = Math.floor(processorOptions.downsampleTo || 16000);
    this.frameMs  = Math.floor(processorOptions.postIntervalMs || 20);
    this.frameLen = Math.floor(this.outRate * this.frameMs / 1000); // 320 @ 20ms

    // If input/output ratio is integer (e.g., 48k→16k), use exact decimation
    this.decim = Math.round(sampleRate / this.outRate);
    this.integerDecim = Math.abs(sampleRate - this.outRate * this.decim) < 1e-6;
    this.phase = 0;

    // Fallback linear resampler state (for 44.1k, etc.)
    this.t = 0;        // accumulator in "out samples" units
    this.prev = 0;

    // Buffer to carve fixed frames out of
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
    const grown = new Float32Array(Math.max(this.buf.length * 2, this.bufLen + n));
    grown.set(this.buf.subarray(0, this.bufLen));
    this.buf = grown;
  }

  _pushSample(v) {
    this._ensureCapacity(1);
    this.buf[this.bufLen++] = v;
  }

  _postFramesIfReady() {
    while (this.bufLen >= this.frameLen) {
      const chunk = new Float32Array(this.frameLen);
      chunk.set(this.buf.subarray(0, this.frameLen));
      // shift remainder left
      this.buf.copyWithin(0, this.frameLen, this.bufLen);
      this.bufLen -= this.frameLen;

      // Post as transferable
      this.port.postMessage({ type: 'audio', samples: chunk, rate: this.outRate, frame_len: this.frameLen }, [chunk.buffer]);
    }
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0 || input[0].length === 0) return true;
    const ch0 = input[0];

    if (this.integerDecim && this.decim >= 1) {
      // Exact 48k -> 16k path (decimate by 3)
      for (let i = 0; i < ch0.length; i++) {
        if ((this.phase++ % this.decim) === 0) this._pushSample(ch0[i]);
      }
    } else {
      // Generic linear resampler (handles 44.1k -> 16k, etc.)
      const inRate = sampleRate;
      const outRate = this.outRate;
      let prev = this.prev;
      for (let i = 0; i < ch0.length; i++) {
        const curr = ch0[i];
        this.t += outRate;
        while (this.t >= inRate) {
          const frac = (this.t - inRate) / outRate;
          const y = prev + (curr - prev) * frac;
          this._pushSample(y);
          this.t -= inRate;
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
