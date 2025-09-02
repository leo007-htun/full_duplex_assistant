// mic-capture-processor.js
class MicCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    this.dstRate = options?.processorOptions?.downsampleTo || 16000;
    this.postMs  = options?.processorOptions?.postIntervalMs || 100; // ~100ms
    this.frameTarget = Math.floor(sampleRate * this.postMs / 1000);
    this.chunks = [];
    this.total  = 0;
  }
  _resampleLinear(f32, srcRate, dstRate) {
    if (srcRate === dstRate) return f32;
    const ratio = dstRate / srcRate;
    const out = new Float32Array(Math.floor(f32.length * ratio));
    let pos = 0;
    for (let i = 0; i < out.length; i++) {
      const idx = pos | 0, frac = pos - idx;
      const a = f32[idx] || 0, b = f32[idx + 1] || a;
      out[i] = a + (b - a) * frac;
      pos += 1 / ratio;
    }
    return out;
  }
  process(inputs, outputs) {
    // keep graph alive, output silence
    const out = outputs[0];
    if (out && out[0]) out[0].fill(0);

    const input = inputs[0];
    if (!input || !input[0]) return true;
    const ch = input[0];
    this.chunks.push(ch.slice());
    this.total += ch.length;

    if (this.total >= this.frameTarget) {
      const buf = new Float32Array(this.total);
      let off = 0;
      for (const c of this.chunks) { buf.set(c, off); off += c.length; }
      this.chunks.length = 0; this.total = 0;

      const down = this._resampleLinear(buf, sampleRate, this.dstRate);
      this.port.postMessage({ type: 'audio', samples: down }, [down.buffer]);
    }
    return true;
  }
}
registerProcessor('mic-capture', MicCaptureProcessor);
