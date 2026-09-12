// Two tiny processors: one turns the mic into 16-bit frames, the other plays
// the agent's 16-bit frames back. Both run at the context rate (24 kHz).

class MicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(0);
    this.frame = 1200; // ~50 ms at 24 kHz
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0]) return true;
    const chunk = input[0];

    const merged = new Float32Array(this.buffer.length + chunk.length);
    merged.set(this.buffer, 0);
    merged.set(chunk, this.buffer.length);
    this.buffer = merged;

    while (this.buffer.length >= this.frame) {
      const slice = this.buffer.subarray(0, this.frame);
      const pcm = new Int16Array(this.frame);
      for (let i = 0; i < this.frame; i++) {
        const s = Math.max(-1, Math.min(1, slice[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
      this.buffer = this.buffer.slice(this.frame);
    }
    return true;
  }
}

class PlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.queue = [];
    this.offset = 0;
    this.port.onmessage = (event) => {
      if (event.data === "flush") {          // barge-in: drop what is unplayed
        this.queue = [];
        this.offset = 0;
        return;
      }
      this.queue.push(new Int16Array(event.data));
    };
  }

  process(_inputs, outputs) {
    const out = outputs[0][0];
    let written = 0;

    while (written < out.length) {
      if (!this.queue.length) {
        out.fill(0, written);
        this.port.postMessage("idle");
        return true;
      }
      const head = this.queue[0];
      const take = Math.min(out.length - written, head.length - this.offset);
      for (let i = 0; i < take; i++) {
        out[written + i] = head[this.offset + i] / 0x8000;
      }
      written += take;
      this.offset += take;
      if (this.offset >= head.length) {
        this.queue.shift();
        this.offset = 0;
      }
    }
    return true;
  }
}

registerProcessor("mic-processor", MicProcessor);
registerProcessor("player-processor", PlayerProcessor);
