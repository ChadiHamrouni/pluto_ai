/**
 * useVoice — microphone recording + backend Whisper STT for the voice conversation loop.
 *
 * Flow (voice mode):
 *   tap Voice → startRecording() → tap Voice again → stopRecording()
 *     → POST /transcribe → onSend(text) fired automatically
 *
 * Flow (dictate / confirm mode — set autoSend=false):
 *   startRecording() → stopRecording() → pendingTranscript set
 *   → user calls confirmSend() or discardTranscript()
 *
 * waveformBars: live frequency bar data (0–1) updated at ~60fps while recording.
 * Built directly inside the hook so the AnalyserNode connects the instant the
 * MediaStream is created — no prop-drilling delay through React state.
 */

import { useRef, useState, useEffect, useCallback } from "react";
import { transcribeAudio } from "../api";

const BAR_COUNT     = 40;
const MIN_AUDIO_BYTES = 1500;

export function useVoice({ onSend, autoSend = true }) {
  const [recording, setRecording]                 = useState(false);
  const [transcribing, setTranscribing]           = useState(false);
  const [pendingTranscript, setPendingTranscript] = useState("");
  const [lastTranscript, setLastTranscript]       = useState("");
  const [waveformBars, setWaveformBars]           = useState(() => new Array(BAR_COUNT).fill(0));

  const mediaRecRef  = useRef(null);
  const chunksRef    = useRef([]);
  const rafRef       = useRef(null);
  const analyserRef  = useRef(null);
  const audioCtxRef  = useRef(null);

  // Stop the waveform RAF loop and close the AudioContext
  function _stopWaveform() {
    cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    if (analyserRef.current) {
      analyserRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close();
      audioCtxRef.current = null;
    }
    setWaveformBars(new Array(BAR_COUNT).fill(0));
  }

  // Start reading frequency data from the stream into waveformBars
  function _startWaveform(stream) {
    try {
      const ctx      = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize               = 256;
      analyser.smoothingTimeConstant = 0.8;
      ctx.createMediaStreamSource(stream).connect(analyser);
      audioCtxRef.current  = ctx;
      analyserRef.current  = analyser;

      // Resume in case the WebView started the AudioContext in suspended state
      if (ctx.state === "suspended") {
        ctx.resume().catch((e) => console.warn("[useVoice] AudioContext resume failed:", e));
      }

      const buf  = new Uint8Array(analyser.frequencyBinCount);
      const step = Math.max(1, Math.floor(buf.length / BAR_COUNT));

      function tick() {
        if (!analyserRef.current) return; // stopped — bail out
        analyserRef.current.getByteFrequencyData(buf);
        const bars = Array.from({ length: BAR_COUNT }, (_, i) => buf[i * step] / 255);
        setWaveformBars(bars);
        rafRef.current = requestAnimationFrame(tick);
      }
      rafRef.current = requestAnimationFrame(tick);
    } catch (e) {
      console.warn("[useVoice] Waveform init failed:", e.message);
    }
  }

  async function _transcribeAudio() {
    const mimeType = mediaRecRef.current?.mimeType || "audio/webm";
    const blob = new Blob(chunksRef.current, { type: mimeType });
    if (blob.size < MIN_AUDIO_BYTES) {
      console.debug("[useVoice] Skipping transcription — blob too small (%d bytes)", blob.size);
      setTranscribing(false);
      return;
    }
    try {
      const text = await transcribeAudio(blob);
      setLastTranscript(text);
      if (text) {
        if (autoSend) {
          onSend(text);
        } else {
          setPendingTranscript(text);
        }
      }
    } catch (e) {
      console.error("[useVoice] Transcription error:", e.message);
    } finally {
      setTranscribing(false);
    }
  }

  async function startRecording() {
    if (recording) return;
    setPendingTranscript("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      _startWaveform(stream);

      // Pick a mimeType the browser actually supports
      const PREFERRED_TYPES = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/ogg;codecs=opus",
        "audio/mp4",
      ];
      const mimeType = PREFERRED_TYPES.find((t) => MediaRecorder.isTypeSupported(t)) || "";

      chunksRef.current   = [];
      mediaRecRef.current = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mediaRecRef.current.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        _stopWaveform();
        _transcribeAudio();
      };
      // 250 ms timeslice — ensures audio frames are flushed continuously
      // so the blob has real data even for short recordings
      mediaRecRef.current.start(250);
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

  // Cleanup on unmount
  useEffect(() => () => {
    mediaRecRef.current?.stop();
    _stopWaveform();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /** Send the pending transcript (only used when autoSend=false). */
  function confirmSend() {
    if (!pendingTranscript) return;
    const text = pendingTranscript;
    setPendingTranscript("");
    onSend(text);
  }

  function discardTranscript() {
    setPendingTranscript("");
  }

  return {
    recording,
    transcribing,
    pendingTranscript,
    lastTranscript,
    waveformBars,
    startRecording,
    stopRecording,
    confirmSend,
    discardTranscript,
  };
}
