import { useState, useRef, useEffect } from "react";
import { sendMessage, startAutonomous, cancelAutonomous, streamAutonomous } from "./api";
import { useVoice } from "./hooks/useVoice";
import { useFileDrop } from "./hooks/useFileDrop";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import Header from "./components/Header";
import ChatFooter from "./components/ChatFooter";
import StatusLabel from "./components/StatusLabel";
import PlanTracker from "./PlanTracker";
import SettingsPanel from "./components/SettingsPanel";
import "./App.css";

const THINKING_WORDS = [
  "Echkher ya talyena...", "Onfokh el zokra...",
  "Chil aayounak aani", "يا قمر الليل", "ليلة و المزود خدام",
  "ام الشعور السود", "نمدح الأقطاب ", "يامه الأسمر دوني",
];

export default function App() {
  const [messages, setMessages]       = useState([]);
  const [input, setInput]             = useState("");
  const [thinking, setThinking]       = useState(false);
  const [error, setError]             = useState(null);
  const [attachments, setAttachments] = useState([]);
  const [dragging, setDragging]       = useState(false);
  const [autoMode, setAutoMode]       = useState(false);
  const [currentPlan, setCurrentPlan] = useState(null);
  const [showSettings, setShowSettings] = useState(false);

  const bottomRef    = useRef(null);
  const inputRef     = useRef(null);
  const canvasRef    = useRef(null);
  const autoTaskIdRef = useRef(null);
  const autoEsRef    = useRef(null);

  // ── Auto-scroll + autofocus ────────────────────────────────────────────────
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, thinking]);
  useEffect(() => { inputRef.current?.focus(); }, []);

  // ── Hooks ──────────────────────────────────────────────────────────────────
  const { recording, transcribing, toggle: toggleVoice } = useVoice({
    canvasRef,
    onTranscript: (text) => {
      setInput((prev) => (prev ? prev + " " + text : text));
      inputRef.current?.focus();
    },
  });

  useFileDrop({
    onDragging: setDragging,
    onFile:     (att) => { setAttachments((prev) => [...prev, att]); inputRef.current?.focus(); },
    onError:    setError,
  });

  useKeyboardShortcuts([
    {
      combo: ["ctrlKey", "l"],
      handler: () => { setAutoMode((p) => !p); setCurrentPlan(null); },
      deps: [],
    },
    {
      combo: ["ctrlKey", "v"],
      handler: toggleVoice,
      condition: !thinking && !transcribing,
      deps: [recording, thinking, transcribing],
    },
  ]);

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
    if (inputRef.current) inputRef.current.style.height = "auto";
    setError(null);

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
          (event) => { if (event.plan) setCurrentPlan(event.plan); },
          (event) => {
            if (event?.plan) setCurrentPlan(event.plan);
            autoTaskIdRef.current = null;
            autoEsRef.current = null;
            setThinking(false);
            const failed  = event?.plan?.steps?.filter((s) => s.status === "failed") ?? [];
            const summary = event?.plan?.status === "completed"
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

    const sentAttachments = attachments;
    setAttachments([]);
    setMessages((prev) => [...prev, {
      role: "user",
      content: text || "(image)",
      previews: sentAttachments.map((a) => a.preview),
    }]);
    setThinking(true);

    const tryFetch = async () => {
      try {
        const reply = await sendMessage(text || "(describe this image)", sentAttachments.map((a) => a.file));
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

  function handleInputChange(e) {
    setInput(e.target.value);
    const el = e.target;
    el.style.height = "auto";
    el.style.height = el.scrollHeight + "px";
  }

  function removeAttachment(index) {
    URL.revokeObjectURL(attachments[index].preview);
    setAttachments((prev) => prev.filter((_, i) => i !== index));
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className={`layout ${dragging ? "drag-over" : ""}`}>
      {dragging && (
        <div className="drag-overlay">
          <div className="drag-overlay-inner">
            <span className="drag-icon">🖼</span>
            <p>Drop image or PDF to attach</p>
          </div>
        </div>
      )}

      <Header autoMode={autoMode} onSettings={() => setShowSettings(true)} />
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}

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
              {m.previews?.map((p, j) => (
                <img key={j} src={p} alt="attachment" className="bubble-img" />
              ))}
              {m.content !== "(image)" && <p className="bubble-text">{m.content}</p>}
            </div>
          </div>
        ))}

        {currentPlan && <PlanTracker plan={currentPlan} onCancel={handleAutoCancel} />}

        {thinking && (
          <div className="bubble-row assistant">
            <div className="bubble">
              <span className="bubble-label">Jarvis</span>
              <StatusLabel words={currentPlan ? ["Executing plan…", "Running step…", "Working on it…"] : THINKING_WORDS} />
            </div>
          </div>
        )}

        {error && <div className="error-row"><span>{error}</span></div>}
        <div ref={bottomRef} />
      </main>

      <ChatFooter
        input={input}
        onInputChange={handleInputChange}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
        thinking={thinking}
        attachments={attachments}
        onRemoveAttachment={removeAttachment}
        recording={recording}
        transcribing={transcribing}
        onVoiceToggle={toggleVoice}
        canvasRef={canvasRef}
        autoMode={autoMode}
        onAutoToggle={() => { setAutoMode((p) => !p); setCurrentPlan(null); }}
      />
    </div>
  );
}
