import { pipeline, env } from "@huggingface/transformers";

// Disable multithreading (required workaround for onnxruntime-web bug in WebView2)
env.backends.onnx.wasm.numThreads = 1;

class WhisperPipeline {
  static task = "automatic-speech-recognition";
  static model = "onnx-community/whisper-tiny.en";
  static instance = null;

  static async getInstance(progress_callback = null) {
    if (this.instance === null) {
      this.instance = await pipeline(this.task, this.model, {
        dtype: "q8",
        progress_callback,
      });
    }
    return this.instance;
  }
}

self.addEventListener("message", async (event) => {
  const transcriber = await WhisperPipeline.getInstance((data) => {
    self.postMessage({ status: "loading", data });
  });

  const result = await transcriber(event.data.audio, {
    return_timestamps: false,
    language: "english",
    task: "transcribe",
  });

  self.postMessage({ status: "complete", text: result.text.trim() });
});
