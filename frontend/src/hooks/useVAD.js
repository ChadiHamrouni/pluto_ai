/**
 * useVAD — Voice Activity Detection for barge-in support.
 *
 * Uses @ricky0123/vad-react (Silero VAD v5, ONNX Runtime Web).
 *
 * IMPORTANT: useMicVAD initialises ONNX + AudioWorklet on mount regardless of
 * startOnLoad. To avoid crashing on startup (black screen in Tauri WebView2),
 * this hook does NOT call useMicVAD directly. Instead it exports a <VADListener>
 * component that is only rendered when voiceMode is true — so the ONNX model
 * never loads until the user actually enters voice mode.
 *
 * Usage in App.jsx:
 *   import { VADListener } from "./hooks/useVAD";
 *   {voiceMode && <VADListener speaking={speaking} stopTTS={stopTTS} startRec={startRec} stopRec={stopRec} />}
 */

import { useEffect, useRef } from "react";
import { useMicVAD } from "@ricky0123/vad-react";

/**
 * Inner component — only rendered when voiceMode is active.
 * Mounts ONNX/worklet, listens for speech, handles barge-in.
 */
export function VADListener({ speaking, stopTTS, startRec, stopRec }) {
  const suppressRef = useRef(false);

  useEffect(() => {
    suppressRef.current = speaking;
  }, [speaking]);

  useMicVAD({
    startOnLoad: true,
    workletURL:  "/vad.worklet.bundle.min.js",
    modelURL:    "/silero_vad_v5.onnx",
    ortConfig:   (ort) => { ort.env.wasm.wasmPaths = "/"; },
    startOnSpeechProbability: 0.8,
    endOnSpeechProbability:   0.3,
    minSpeechFrames:          3,

    onSpeechStart: () => {
      if (suppressRef.current) {
        stopTTS();
        startRec();
        return;
      }
      startRec();
    },

    onSpeechEnd:   () => stopRec(),
    onVADMisfire:  () => stopRec(),
  });

  return null;
}
