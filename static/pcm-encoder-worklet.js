class PCMEncoderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    // 100 ms of mono audio at 16 kHz → 1 600 samples
    this.samplesPerChunk = 1600;
  }

  process(inputs) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0];
      for (let i = 0; i < channelData.length; i++) {
        // clamp sample to [-1,1] then convert to 16-bit signed integer
        const s = Math.max(-1, Math.min(1, channelData[i]));
        this.buffer.push(s * 32767);
        if (this.buffer.length === this.samplesPerChunk) {
          const int16 = new Int16Array(this.buffer);
          this.port.postMessage(int16.buffer, [int16.buffer]);
          this.buffer = [];
        }
      }
    }
    return true; // keep processor alive
  }
}

registerProcessor('pcm-encoder', PCMEncoderProcessor);
