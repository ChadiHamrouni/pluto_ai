import { pipeline, env } from "@huggingface/transformers";

// Disable multithreading (required workaround for onnxruntime-web bug in WebView2)
env.backends.onnx.wasm.numThreads = 1;

const MODEL    = import.meta.env.VITE_WHISPER_MODEL    ?? "onnx-community/whisper-tiny.en";
const DTYPE    = import.meta.env.VITE_WHISPER_DTYPE    ?? "q8";
const LANGUAGE = import.meta.env.VITE_WHISPER_LANGUAGE ?? "english";

class WhisperPipeline {
  static task = "automatic-speech-recognition";
  static instance = null;

  static async getInstance(progress_callback = null) {
    if (this.instance === null) {
      this.instance = await pipeline(this.task, MODEL, {
        dtype: DTYPE,
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
    language: LANGUAGE,
    task: "transcribe",
  });

  self.postMessage({ status: "complete", text: result.text.trim() });
});
