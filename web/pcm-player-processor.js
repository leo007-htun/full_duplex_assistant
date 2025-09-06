// Simple PCM Float32 player worklet.
// Receives messages: { type: 'audio', samples: Float32Array } and { type: 'flush' }.
class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];         // array of Float32Array chunks
    this.readIndex = 0;      // index into current chunk
    this.current = null;

    this.port.onmessage = (e) => {
      const msg = e.data || {};
      if (msg.type === 'audio' && msg.samples && msg.samples.buffer) {
        // Expect a Float32Array
        const f32 = msg.samples;
        if (f32.length > 0) this.queue.push(f32);
      } else if (msg.type === 'flush') {
        this.queue = [];
        this.current = null;
        this.readIndex = 0;
      }
    };
  }

  _pullFrame(length) {
    const out = new Float32Array(length);
    let written = 0;

    while (written < length) {
      if (!this.current || this.readIndex >= this.current.length) {
        // advance to next chunk if available
        this.current = this.queue.length ? this.queue.shift() : null;
        this.readIndex = 0;
        if (!this.current) break; // no data; remaining will be zeros
      }
      const remainOut = length - written;
      const remainCur = this.current.length - this.readIndex;
      const toCopy = Math.min(remainOut, remainCur);
      out.set(this.current.subarray(this.readIndex, this.readIndex + toCopy), written);
      this.readIndex += toCopy;
      written += toCopy;
    }
    // any leftover stays zero
    return out;
  }

  process(_inputs, outputs) {
    const output = outputs[0];
    if (!output || output.length === 0) return true;

    const ch0 = output[0];
    const frame = this._pullFrame(ch0.length);

    // mono to all channels (usually 1 channel anyway)
    for (let c = 0; c < output.length; c++) {
      output[c].set(frame);
    }
    return true;
  }
}

registerProcessor('pcm-player', PCMPlayer);
