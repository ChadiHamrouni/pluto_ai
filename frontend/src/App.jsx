import { useState, useRef, useEffect } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { getCurrentWebview } from "@tauri-apps/api/webview";
import { readFile } from "@tauri-apps/plugin-fs";
import { sendMessage, startAutonomous, cancelAutonomous, streamAutonomous } from "./api";
import PlanTracker from "./PlanTracker";
import "./App.css";

const THINKING_WORDS = [
 "Echkher ya talyena...", "Onfokh el zokra...",
  "Chil aayounak aani", "يا قمر الليل", "ليلة و المزود خدام", "ام الشعور السود", "نمدح الأقطاب ", "يامه الأسمر دوني"
];

const TRANSCRIBING_WORDS = [
  "Transcribing", "Listening", "Parsing", "Decoding",
  "Converting", "Reading", "Interpreting",
];

function StatusLabel({ words }) {
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState("in"); // "in" | "hold" | "out"
  const [stars, setStars] = useState([]);

  // Spawn a new star particle
  function spawnStar() {
    const id = Math.random();
    const x = Math.random() * 14;
    const y = Math.random() * 14;
    const size = 7 + Math.random() * 7;
    const delay = Math.random() * 0.4;
    setStars((prev) => [...prev.slice(-5), { id, x, y, size, delay }]);
    setTimeout(() => setStars((prev) => prev.filter((s) => s.id !== id)), 900);
  }

  // Continuous star loop
  useEffect(() => {
    const loop = setInterval(() => {
      spawnStar();
    }, 350);
    return () => clearInterval(loop);
  }, []);

  // Word cycling
  useEffect(() => {
    let t1, t2;
    const cycle = setInterval(() => {
      setPhase("out");
      t1 = setTimeout(() => {
        setIndex((i) => (i + 1) % words.length);
        setPhase("in");
        t2 = setTimeout(() => setPhase("hold"), 500);
      }, 500);
    }, 4000);

    setTimeout(() => setPhase("hold"), 500);

    return () => {
      clearInterval(cycle);
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [words]);

  return (
    <span className="status-container">
      <span className={`status-word status-${phase}`}>
        {words[index]}
      </span>
      <span className="status-stars" aria-hidden="true">
        {stars.map((s) => (
          <svg
            key={s.id}
            className="status-star"
            style={{ left: s.x, top: s.y, width: s.size, height: s.size, animationDelay: `${s.delay}s` }}
            viewBox="0 0 24 24"
          >
            <polygon
              points="12,2 14.5,9.5 22,9.5 16,14.5 18.5,22 12,17.5 5.5,22 8,14.5 2,9.5 9.5,9.5"
              fill="var(--neon)"
            />
          </svg>
        ))}
      </span>
    </span>
  );
}

export default function App() {
  const [messages, setMessages]     = useState([]);
  const [input, setInput]           = useState("");
  const [thinking, setThinking]     = useState(false);
  const [error, setError]           = useState(null);
  const [attachments, setAttachments] = useState([]);
  const [dragging, setDragging]     = useState(false);
  const [recording, setRecording]   = useState(false);
  const [expanded, setExpanded]     = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [autoMode, setAutoMode]     = useState(false);
  const [currentPlan, setCurrentPlan] = useState(null);
  const autoTaskIdRef = useRef(null);
  const autoEsRef     = useRef(null);

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

  // ── Autofocus input on mount ───────────────────────────────────────────────
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // ── Ctrl+I → toggle maximize ───────────────────────────────────────────────
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey && e.key === "i") {
        e.preventDefault();
        handleExpand();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  // ── Ctrl+L → toggle autonomous mode ───────────────────────────────────────
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey && e.key === "l") {
        e.preventDefault();
        setAutoMode((prev) => !prev);
        setCurrentPlan(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // ── Ctrl+V → toggle voice recording ───────────────────────────────────────
  useEffect(() => {
    const onKey = (e) => {
      if (e.ctrlKey && e.key === "v" && !thinking && !transcribing) {
        e.preventDefault();
        handleVoiceBtn();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [recording, thinking, transcribing]);

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

  // ── Drag-and-drop via Tauri v2 webview API ────────────────────────────────
  useEffect(() => {
    let unlisten;

    const setup = async () => {
      unlisten = await getCurrentWebview().onDragDropEvent(async (event) => {
        const type = event.payload.type;

        if (type === "over") {
          setDragging(true);
        } else if (type === "cancelled") {
          setDragging(false);
        } else if (type === "drop") {
          setDragging(false);
          const paths = event.payload.paths;
          if (!paths || paths.length === 0) return;

          const filePath = paths[0];
          const ext = filePath.split(".").pop().toLowerCase();
          const imageExts = ["jpg", "jpeg", "png", "webp", "gif", "bmp"];
          const supported = [...imageExts, "pdf", "txt"];
          if (!supported.includes(ext)) {
            setError("Supported files: images, PDFs, and .txt files.");
            return;
          }

          try {
            const bytes = await readFile(filePath);
            const mimeMap = {
              jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png",
              webp: "image/webp", gif: "image/gif", bmp: "image/bmp",
              pdf: "application/pdf",
              txt: "text/plain",
            };
            const mime = mimeMap[ext] || "application/octet-stream";
            const blob = new Blob([bytes], { type: mime });
            const fileName = filePath.split(/[\\/]/).pop();
            const file = new File([blob], fileName, { type: mime });
            const preview = ext === "pdf" ? null : URL.createObjectURL(blob);
            const isNonImage = ext === "pdf" || ext === "txt";
            setAttachments((prev) => [...prev, { file, preview: isNonImage ? null : preview, isPdf: isNonImage, fileExt: ext }]);
            inputRef.current?.focus();
          } catch (e) {
            setError("Failed to read file: " + e.message);
          }
        }
      });
    };

    setup();
    return () => { unlisten?.(); };
  }, []);

  // ── Autonomous cancel ──────────────────────────────────────────────────────
  async function handleAutoCancel() {
    if (autoTaskIdRef.current) {
      await cancelAutonomous(autoTaskIdRef.current);
      autoTaskIdRef.current = null;
    }
    autoEsRef.current?.close();
    autoEsRef.current = null;
    setThinking(false);
  }

  // ── Send ───────────────────────────────────────────────────────────────────
  async function handleSend() {
    const text = input.trim();
    if ((!text && !attachments.length) || thinking) return;

    setInput("");
    resetInputHeight();
    setError(null);

    // ── Autonomous mode ────────────────────────────────────────────────────
    if (autoMode && text) {
      setAttachments([]);
      setMessages((prev) => [...prev, { role: "user", content: `[AUTO] ${text}` }]);
      setThinking(true);
      setCurrentPlan(null);

      try {
        const { task_id } = await startAutonomous(text);
        autoTaskIdRef.current = task_id;

        const es = streamAutonomous(
          task_id,
          (event) => {
            if (event.plan) setCurrentPlan(event.plan);
          },
          (event) => {
            if (event?.plan) setCurrentPlan(event.plan);
            autoTaskIdRef.current = null;
            autoEsRef.current = null;
            setThinking(false);
            const failed = event?.plan?.steps?.filter((s) => s.status === "failed") ?? [];
            const done = event?.plan?.status === "completed";
            const summary = done
              ? `Autonomous task completed${failed.length ? ` (${failed.length} step(s) failed)` : ""}.`
              : "Autonomous task stopped.";
            setMessages((prev) => [...prev, { role: "assistant", content: summary }]);
            inputRef.current?.focus();
          }
        );
        autoEsRef.current = es;
      } catch (e) {
        setError(e.message);
        setThinking(false);
      }
      return;
    }

    // ── Normal mode ────────────────────────────────────────────────────────
    const sentAttachments = attachments;
    setAttachments([]);
    setMessages((prev) => [
      ...prev,
      {
        role: "user",
        content: text || "(image)",
        previews: sentAttachments.map((a) => a.preview),
      },
    ]);
    setThinking(true);

    const tryFetch = async () => {
      try {
        const reply = await sendMessage(
          text || "(describe this image)",
          sentAttachments.map((a) => a.file)
        );
        setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
        setThinking(false);
        inputRef.current?.focus();
      } catch (e) {
        if (e.message === "Failed to fetch") {
          setTimeout(tryFetch, 3000);
        } else {
          setError(e.message);
          setThinking(false);
          inputRef.current?.focus();
        }
      }
    };

    tryFetch();
  }

  function handleKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function handleInputChange(e) {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }

  function resetInputHeight() {
    if (inputRef.current) inputRef.current.style.height = "auto";
  }

  function removeAttachment(index) {
    URL.revokeObjectURL(attachments[index].preview);
    setAttachments((prev) => prev.filter((_, i) => i !== index));
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
            <p>Drop image or PDF to attach</p>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="header" data-tauri-drag-region>
        <div className="header-left" data-tauri-drag-region>
          <span className="header-title" data-tauri-drag-region>JARVIS</span>
          <span className="header-sub" data-tauri-drag-region>
            {autoMode ? "autonomous mode" : "personal assistant"}
          </span>
          {autoMode && (
            <span className="header-auto-badge" data-tauri-drag-region>AUTO</span>
          )}
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
              {m.previews?.map((p, i) => (
                <img key={i} src={p} alt="attachment" className="bubble-img" />
              ))}
              {m.content !== "(image)" && (
                <p className="bubble-text">{m.content}</p>
              )}
            </div>
          </div>
        ))}

        {currentPlan && (
          <PlanTracker plan={currentPlan} onCancel={handleAutoCancel} />
        )}

        {thinking && !currentPlan && (
          <div className="bubble-row assistant">
            <div className="bubble">
              <span className="bubble-label">Jarvis</span>
              <StatusLabel words={THINKING_WORDS} />
            </div>
          </div>
        )}

        {thinking && currentPlan && (
          <div className="bubble-row assistant">
            <div className="bubble">
              <span className="bubble-label">Jarvis</span>
              <StatusLabel words={["Executing plan…", "Running step…", "Working on it…"]} />
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
        {/* Attachment previews */}
        {attachments.length > 0 && (
          <div className="attachment-bar">
            {attachments.map((a, i) => (
              <div key={i} className="attachment-item">
                {a.isPdf
                  ? <span className="attachment-pdf-icon">{a.fileExt?.toUpperCase() || "FILE"}</span>
                  : <img src={a.preview} alt="attachment preview" className="attachment-thumb" />
                }
                <span className="attachment-name">{a.file.name}</span>
                <button className="attachment-remove" onClick={() => removeAttachment(i)}>✕</button>
              </div>
            ))}
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
            <StatusLabel words={TRANSCRIBING_WORDS} />
          </div>
        )}

        <div className="input-row">
          <textarea
            ref={inputRef}
            className="msg-input"
            placeholder={
            autoMode
              ? "Describe a multi-step task for Jarvis to plan and execute…"
              : attachments.length ? "Add a message… (or just Enter)" : "Message Jarvis…"
          }
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKey}
            disabled={thinking}
          />
          <div className="mic-stack">
            <button
              className={`auto-toggle ${autoMode ? "auto-toggle--on" : ""}`}
              onClick={() => { setAutoMode((p) => !p); setCurrentPlan(null); }}
              title={autoMode ? "Autonomous mode ON — click to disable" : "Click to enable autonomous mode"}
            >
              {autoMode ? "AUTO" : "AUTO"}
            </button>
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
        </div>
        <p className="hint">
          {autoMode
            ? "Ctrl+L to exit autonomous mode · Enter to run plan"
            : "Shift+Enter for newline · Ctrl+L for autonomous mode · Drop image, PDF, or TXT to attach"}
        </p>
      </footer>
    </div>
  );
}
