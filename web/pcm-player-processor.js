class PCMPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];       // array of Float32Array chunks
    this.readIdx = 0;

    this.port.onmessage = (e) => {
      const { type, samples } = e.data || {};
      if (type === "audio" && samples) {
        // samples is a Float32Array
        this.queue.push(samples);
      } else if (type === "flush") {
        this.queue.length = 0;
        this.readIdx = 0;
      }
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0][0]; // mono
    let i = 0;

    while (i < out.length) {
      if (this.queue.length === 0) {
        // no data -> play silence to keep clock running
        out[i++] = 0;
        continue;
      }
      const chunk = this.queue[0];
      out[i++] = chunk[this.readIdx++];
      if (this.readIdx >= chunk.length) {
        this.queue.shift();
        this.readIdx = 0;
      }
    }
    return true; // keep alive
  }
}
registerProcessor("pcm-player", PCMPlayerProcessor);
