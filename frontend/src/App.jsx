import { useState, useRef, useEffect } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { listen } from "@tauri-apps/api/event";
import { readFile } from "@tauri-apps/plugin-fs";
import { sendMessage } from "./api";
import "./App.css";

export default function App() {
  const [messages, setMessages]     = useState([]);
  const [input, setInput]           = useState("");
  const [thinking, setThinking]     = useState(false);
  const [error, setError]           = useState(null);
  const [attachment, setAttachment] = useState(null);
  const [dragging, setDragging]     = useState(false);
  const [recording, setRecording]   = useState(false);
  const [expanded, setExpanded]     = useState(false);
  const [transcribing, setTranscribing] = useState(false);

  const bottomRef    = useRef(null);
  const inputRef     = useRef(null);
  const workerRef    = useRef(null);
  const mediaRecRef  = useRef(null);
  const audioCtxRef  = useRef(null);
  const analyserRef  = useRef(null);
  const sourceRef    = useRef(null);
  const chunksRef    = useRef([]);
  const canvasRef    = useRef(null);
  const rafRef       = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  // ── Init Whisper worker ────────────────────────────────────────────────────
  useEffect(() => {
    workerRef.current = new Worker(
      new URL("./worker.js", import.meta.url),
      { type: "module" }
    );

    workerRef.current.onmessage = (e) => {
      if (e.data.status === "complete") {
        setTranscribing(false);
        const text = e.data.text;
        if (text) {
          setInput((prev) => (prev ? prev + " " + text : text));
          inputRef.current?.focus();
        }
      }
    };

    return () => workerRef.current?.terminate();
  }, []);

  // ── Start wave once canvas is mounted (recording state = true) ────────────
  useEffect(() => {
    if (recording) drawWave();
  }, [recording]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Wave visualizer ────────────────────────────────────────────────────────
  function drawWave() {
    const canvas = canvasRef.current;
    const analyser = analyserRef.current;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext("2d");
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const render = () => {
      rafRef.current = requestAnimationFrame(render);
      analyser.getByteTimeDomainData(dataArray);

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      ctx.lineWidth = 1.5;
      ctx.strokeStyle = "#00c8ff";
      ctx.shadowBlur = 4;
      ctx.shadowColor = "#00c8ff";
      ctx.beginPath();

      const sliceWidth = canvas.width / bufferLength;
      let x = 0;
      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * canvas.height) / 2;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        x += sliceWidth;
      }
      ctx.lineTo(canvas.width, canvas.height / 2);
      ctx.stroke();
    };

    render();
  }

  function stopWave() {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    const canvas = canvasRef.current;
    if (canvas) {
      const ctx = canvas.getContext("2d");
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
  }

  // ── Voice recording ────────────────────────────────────────────────────────
  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      // Audio context for visualizer
      audioCtxRef.current = new AudioContext();
      analyserRef.current = audioCtxRef.current.createAnalyser();
      analyserRef.current.fftSize = 1024;
      sourceRef.current = audioCtxRef.current.createMediaStreamSource(stream);
      sourceRef.current.connect(analyserRef.current);

      // MediaRecorder to capture raw audio
      chunksRef.current = [];
      mediaRecRef.current = new MediaRecorder(stream);
      mediaRecRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      mediaRecRef.current.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        audioCtxRef.current?.close();
        transcribeAudio();
      };

      mediaRecRef.current.start();
      setRecording(true);
    } catch (e) {
      setError("Microphone access denied: " + e.message);
    }
  }

  function stopRecording() {
    mediaRecRef.current?.stop();
    stopWave();
    setRecording(false);
    setTranscribing(true);
  }

  async function transcribeAudio() {
    const blob = new Blob(chunksRef.current, { type: "audio/webm" });
    const arrayBuffer = await blob.arrayBuffer();

    // Decode to Float32Array at 16kHz mono (what Whisper expects)
    const decodeCtx = new AudioContext({ sampleRate: 16000 });
    const audioBuffer = await decodeCtx.decodeAudioData(arrayBuffer);
    decodeCtx.close();

    const float32 = audioBuffer.getChannelData(0);
    workerRef.current.postMessage({ audio: float32 }, [float32.buffer]);
  }

  function handleVoiceBtn() {
    if (recording) {
      stopRecording();
    } else {
      startRecording();
    }
  }

  // ── Drag-and-drop via Tauri file drop events ───────────────────────────────
  useEffect(() => {
    let unlistenHover, unlistenDrop, unlistenCancel;

    const setup = async () => {
      unlistenHover = await listen("tauri://file-drop-hover", () => {
        setDragging(true);
      });

      unlistenDrop = await listen("tauri://file-drop", async (event) => {
        setDragging(false);
        const paths = event.payload;
        if (!paths || paths.length === 0) return;

        const filePath = paths[0];
        const ext = filePath.split(".").pop().toLowerCase();
        const imageExts = ["jpg", "jpeg", "png", "webp", "gif", "bmp"];
        if (!imageExts.includes(ext)) {
          setError("Only image files are supported right now.");
          return;
        }

        try {
          const bytes = await readFile(filePath);
          const mimeMap = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", gif: "image/gif", bmp: "image/bmp" };
          const mime = mimeMap[ext] || "image/png";
          const blob = new Blob([bytes], { type: mime });
          const fileName = filePath.split(/[\\/]/).pop();
          const file = new File([blob], fileName, { type: mime });
          const preview = URL.createObjectURL(blob);
          setAttachment({ file, preview });
          inputRef.current?.focus();
        } catch (e) {
          setError("Failed to read image: " + e.message);
        }
      });

      unlistenCancel = await listen("tauri://file-drop-cancelled", () => {
        setDragging(false);
      });
    };

    setup();
    return () => {
      unlistenHover?.();
      unlistenDrop?.();
      unlistenCancel?.();
    };
  }, []);

  // ── Send ───────────────────────────────────────────────────────────────────
  const history = messages.map((m) => ({ role: m.role, content: m.content }));

  async function handleSend() {
    const text = input.trim();
    if ((!text && !attachment) || thinking) return;

    const sentAttachment = attachment;
    setInput("");
    setAttachment(null);
    setError(null);
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: text || "(image)",
        preview: sentAttachment?.preview ?? null,
      },
    ]);
    setThinking(true);

    try {
      const reply = await sendMessage(text || "(describe this image)", history, sentAttachment?.file ?? null);
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (e) {
      setError(e.message);
    } finally {
      setThinking(false);
      inputRef.current?.focus();
    }
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function removeAttachment() {
    if (attachment?.preview) URL.revokeObjectURL(attachment.preview);
    setAttachment(null);
  }

  async function handleClose() {
    await getCurrentWindow().close();
  }

  async function handleExpand() {
    const win = getCurrentWindow();
    await win.toggleMaximize();
    setExpanded(await win.isMaximized());
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className={`layout ${dragging ? "drag-over" : ""}`}>
      {/* Drag overlay */}
      {dragging && (
        <div className="drag-overlay">
          <div className="drag-overlay-inner">
            <span className="drag-icon">🖼</span>
            <p>Drop image to attach</p>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="header" data-tauri-drag-region>
        <div className="header-left" data-tauri-drag-region>
          <span className="header-title" data-tauri-drag-region>JARVIS</span>
          <span className="header-sub" data-tauri-drag-region>personal assistant</span>
        </div>
        <div className="header-actions">
          <button className="expand-btn" onClick={handleExpand} title={expanded ? "Collapse" : "Expand"}>
            {expanded ? (
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <polyline points="9,1 13,1 13,5" /><line x1="8" y1="6" x2="13" y2="1" />
                <polyline points="5,13 1,13 1,9" /><line x1="6" y1="8" x2="1" y2="13" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <polyline points="8,1 13,1 13,6" /><line x1="7" y1="7" x2="13" y2="1" />
                <polyline points="6,13 1,13 1,8" /><line x1="7" y1="7" x2="1" y2="13" />
              </svg>
            )}
          </button>
          <button className="close-btn" onClick={handleClose}>✕</button>
        </div>
      </header>

      {/* Chat */}
      <main className="chat">
        {messages.length === 0 && !thinking && (
          <div className="empty">
            <div className="empty-glow" />
            <p className="empty-text">At your service. How can I help?</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`bubble-row ${m.role}`}>
            <div className="bubble">
              {m.role === "assistant" && <span className="bubble-label">Jarvis</span>}
              {m.preview && (
                <img src={m.preview} alt="attachment" className="bubble-img" />
              )}
              {m.content !== "(image)" && (
                <p className="bubble-text">{m.content}</p>
              )}
            </div>
          </div>
        ))}

        {thinking && (
          <div className="bubble-row assistant">
            <div className="bubble">
              <span className="bubble-label">Jarvis</span>
              <span className="dots"><span /><span /><span /></span>
            </div>
          </div>
        )}

        {error && (
          <div className="error-row"><span>{error}</span></div>
        )}

        <div ref={bottomRef} />
      </main>

      {/* Footer */}
      <footer className="footer">
        {/* Attachment preview */}
        {attachment && (
          <div className="attachment-bar">
            <img src={attachment.preview} alt="attachment preview" className="attachment-thumb" />
            <span className="attachment-name">{attachment.file.name}</span>
            <button className="attachment-remove" onClick={removeAttachment}>✕</button>
          </div>
        )}

        {/* Wave visualizer — only visible while recording */}
        {recording && (
          <div className="wave-container">
            <canvas ref={canvasRef} className="wave-canvas" width={340} height={48} />
          </div>
        )}

        {/* Transcribing indicator */}
        {transcribing && (
          <div className="transcribing-row">
            <span className="dots"><span /><span /><span /></span>
            <span className="transcribing-label">transcribing…</span>
          </div>
        )}

        <div className="input-row">
          <textarea
            ref={inputRef}
            className="msg-input"
            placeholder={attachment ? "Add a message… (or just Send)" : "Message Jarvis…"}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            rows={1}
            disabled={thinking}
          />
          <button
            className={`voice-btn ${recording ? "recording" : ""}`}
            onClick={handleVoiceBtn}
            disabled={thinking || transcribing}
            title={recording ? "Stop recording" : "Voice input"}
          >
            {recording ? (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <rect x="3" y="3" width="10" height="10" rx="2" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <rect x="5" y="1" width="6" height="9" rx="3" />
                <path d="M2.5 8a5.5 5.5 0 0 0 11 0" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
                <line x1="8" y1="13.5" x2="8" y2="15.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            )}
          </button>
        </div>
        <p className="hint">Shift+Enter for newline · Drop image to attach</p>
      </footer>
    </div>
  );
}
