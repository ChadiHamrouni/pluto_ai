import { useRef, useState, useEffect } from "react";

/**
 * Handles microphone recording, waveform visualisation, and Whisper transcription.
 * Returns state + controls to be wired into the UI.
 */
export function useVoice({ onTranscript, canvasRef }) {
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);

  const workerRef   = useRef(null);
  const mediaRecRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef   = useRef(null);
  const chunksRef   = useRef([]);
  const rafRef      = useRef(null);

  // Init Whisper worker once
  useEffect(() => {
    workerRef.current = new Worker(
      new URL("../worker.js", import.meta.url),
      { type: "module" }
    );
    workerRef.current.onmessage = (e) => {
      if (e.data.status === "complete") {
        setTranscribing(false);
        if (e.data.text) onTranscript(e.data.text);
      }
    };
    return () => workerRef.current?.terminate();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Start waveform draw when recording begins
  useEffect(() => {
    if (recording) _drawWave();
  }, [recording]); // eslint-disable-line react-hooks/exhaustive-deps

  function _drawWave() {
    const canvas   = canvasRef.current;
    const analyser = analyserRef.current;
    if (!canvas || !analyser) return;

    const ctx        = canvas.getContext("2d");
    const dataArray  = new Uint8Array(analyser.frequencyBinCount);

    const render = () => {
      rafRef.current = requestAnimationFrame(render);
      analyser.getByteTimeDomainData(dataArray);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.lineWidth    = 1.5;
      ctx.strokeStyle  = "#00c8ff";
      ctx.shadowBlur   = 4;
      ctx.shadowColor  = "#00c8ff";
      ctx.beginPath();
      const sliceWidth = canvas.width / dataArray.length;
      let x = 0;
      for (let i = 0; i < dataArray.length; i++) {
        const y = ((dataArray[i] / 128.0) * canvas.height) / 2;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        x += sliceWidth;
      }
      ctx.lineTo(canvas.width, canvas.height / 2);
      ctx.stroke();
    };
    render();
  }

  function _stopWave() {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    const canvas = canvasRef.current;
    if (canvas) canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
  }

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
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioCtxRef.current  = new AudioContext();
      analyserRef.current  = audioCtxRef.current.createAnalyser();
      analyserRef.current.fftSize = 1024;
      sourceRef.current    = audioCtxRef.current.createMediaStreamSource(stream);
      sourceRef.current.connect(analyserRef.current);

      chunksRef.current    = [];
      mediaRecRef.current  = new MediaRecorder(stream);
      mediaRecRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mediaRecRef.current.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        audioCtxRef.current?.close();
        _transcribeAudio();
      };
      mediaRecRef.current.start();
      setRecording(true);
    } catch (e) {
      throw new Error("Microphone access denied: " + e.message);
    }
  }

  function stopRecording() {
    mediaRecRef.current?.stop();
    _stopWave();
    setRecording(false);
    setTranscribing(true);
  }

  function toggle() {
    recording ? stopRecording() : startRecording();
  }

  return { recording, transcribing, toggle };
}
