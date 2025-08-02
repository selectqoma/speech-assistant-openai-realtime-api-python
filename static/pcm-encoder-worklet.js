// AudioWorklet that captures microphone audio, downsamples to 16 kHz mono PCM-16
// and emits ~100 ms (1 600-sample) buffers for low-latency streaming to OpenAI.

class PCMEncoderProcessor extends AudioWorkletProcessor {
  constructor () {
    super();

    // Browser/device sample-rate (often 48 000 Hz even if we requested 16 000).
    this.inputSampleRate = sampleRate; // `sampleRate` is global inside AudioWorklet
    this.outputSampleRate = 16000;

    this.resampleRatio = this.inputSampleRate / this.outputSampleRate;
    this.frameAccumulator = 0; // counts input frames until we output one frame

    this.outputBuffer = []; // int16 values awaiting send
    this.chunkSize = 3200;  // 200 ms at 16 kHz (well above minimum)
    
    // Debug info
    console.log(`AudioWorklet: Input sample rate: ${this.inputSampleRate}, Output: ${this.outputSampleRate}, Ratio: ${this.resampleRatio}`);
  }

  process (inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;

    const channelData = input[0]; // mono
    let i = 0;
    while (i < channelData.length) {
      if (this.frameAccumulator <= 0) {
        // time to emit a sample
        const s = Math.max(-1, Math.min(1, channelData[i]));
        this.outputBuffer.push(Math.round(s * 32767));
        this.frameAccumulator += this.resampleRatio;

        if (this.outputBuffer.length === this.chunkSize) {
          const pcm16 = new Int16Array(this.outputBuffer);
          console.log(`AudioWorklet: Sending chunk of ${this.chunkSize} samples (${this.chunkSize/16}ms at 16kHz)`);
          this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
          this.outputBuffer = [];
        }
      }

      const step = Math.min(channelData.length - i, this.frameAccumulator);
      i += step;
      this.frameAccumulator -= step;
    }

    return true; // keep processor alive
  }
}

registerProcessor('pcm-encoder', PCMEncoderProcessor);
