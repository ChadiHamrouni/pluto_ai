/**
 * useVoice — microphone recording + Whisper STT for the voice conversation loop.
 *
 * Used exclusively by useVAD (barge-in) and the voice mode pipeline:
 *   VAD detects speech → startRecording() → user stops speaking →
 *   stopRecording() → Whisper transcribes → onSend(text) → agent → TTS
 *
 * The one-shot "record and paste into input" feature has been removed.
 * This hook is only used for the continuous voice mode loop.
 */

import { useRef, useState, useEffect } from "react";

export function useVoice({ onSend }) {
  const [recording, setRecording]       = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [lastTranscript, setLastTranscript] = useState("");

  const workerRef   = useRef(null);
  const mediaRecRef = useRef(null);
  const chunksRef   = useRef([]);

  // Init Whisper worker once
  useEffect(() => {
    workerRef.current = new Worker(
      new URL("../worker.js", import.meta.url),
      { type: "module" }
    );
    workerRef.current.onmessage = (e) => {
      if (e.data.status === "complete") {
        setTranscribing(false);
        if (e.data.text) {
          setLastTranscript(e.data.text);
          onSend(e.data.text);
        }
      }
    };
    return () => workerRef.current?.terminate();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function _transcribeAudio() {
    const blob        = new Blob(chunksRef.current, { type: "audio/webm" });
    const arrayBuffer = await blob.arrayBuffer();
    const decodeCtx   = new AudioContext({ sampleRate: 16000 });
    const audioBuffer = await decodeCtx.decodeAudioData(arrayBuffer);
    decodeCtx.close();
    const float32 = audioBuffer.getChannelData(0);
    workerRef.current.postMessage({ audio: float32 }, [float32.buffer]);
  }

  async function startRecording() {
    if (recording) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      chunksRef.current   = [];
      mediaRecRef.current = new MediaRecorder(stream);
      mediaRecRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mediaRecRef.current.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        _transcribeAudio();
      };
      mediaRecRef.current.start();
      setRecording(true);
    } catch (e) {
      console.error("Microphone access denied:", e.message);
    }
  }

  function stopRecording() {
    if (!recording) return;
    mediaRecRef.current?.stop();
    setRecording(false);
    setTranscribing(true);
  }

  return { recording, transcribing, lastTranscript, startRecording, stopRecording };
}
