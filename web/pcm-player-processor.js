// Receives {type:'audio', samples: Float32Array} and plays them.
// {type:'flush'} clears queued audio immediately.
class PCMPlayer extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = []; // array of Float32Array
    this.readIndex = 0;

    this.port.onmessage = (e) => {
      const msg = e.data || {};
      if (msg.type === 'audio' && msg.samples && msg.samples.buffer) {
        // msg.samples is transferred; take ownership of its buffer
        const f32 = new Float32Array(msg.samples.buffer);
        if (f32.length > 0) this.queue.push(f32);
      } else if (msg.type === 'flush') {
        this.queue = [];
        this.readIndex = 0;
      }
    };
  }

  _pullSample() {
    // Return next sample from queue or 0 if empty
    if (this.queue.length === 0) return 0;
    const curr = this.queue[0];
    const v = curr[this.readIndex++];
    if (this.readIndex >= curr.length) {
      this.queue.shift();
      this.readIndex = 0;
    }
    return v ?? 0;
  }

  process(inputs, outputs) {
    const output = outputs[0];
    if (!output || output.length === 0) return true;
    const ch0 = output[0];
    const ch1 = output.length > 1 ? output[1] : null;

    for (let i = 0; i < ch0.length; i++) {
      const s = this._pullSample();
      ch0[i] = s;
      if (ch1) ch1[i] = s;
    }
    return true;
  }
}

registerProcessor('pcm-player', PCMPlayer);
