import { useState, useRef, useEffect, useCallback } from "react";
import { sendMessage, startAutonomous, cancelAutonomous, streamAutonomous, fetchFile, createSession, setActiveSession, getSessions, getSessionMessages, deleteSession } from "./api";
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";
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

async function downloadFile(fileUrl) {
  try {
    const filename = fileUrl.split("/").pop();
    const savePath = await save({
      defaultPath: filename,
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (!savePath) return;
    const blob = await fetchFile(fileUrl);
    const buffer = await blob.arrayBuffer();
    await writeFile(savePath, new Uint8Array(buffer));
  } catch (e) {
    console.error("Download failed:", e);
  }
}

let _sessionCounter = 0;

function makeSession(id, title = null) {
  _sessionCounter += 1;
  return { id, title: title || `Chat ${_sessionCounter}`, messages: [] };
}

export default function App() {
  const [sessions, setSessions]         = useState([]);
  const [activeId, setActiveId]         = useState(null);
  const [sidebarOpen, setSidebarOpen]   = useState(true);
  const [input, setInput]               = useState("");
  const [thinking, setThinking]         = useState(false);
  const [error, setError]               = useState(null);
  const [attachments, setAttachments]   = useState([]);
  const [dragging, setDragging]         = useState(false);
  const [autoMode, setAutoMode]         = useState(false);
  const [currentPlan, setCurrentPlan]   = useState(null);
  const [showSettings, setShowSettings] = useState(false);

  const bottomRef     = useRef(null);
  const inputRef      = useRef(null);
  const canvasRef     = useRef(null);
  const autoTaskIdRef = useRef(null);
  const autoEsRef     = useRef(null);

  const activeSession = sessions.find(s => s.id === activeId) ?? null;
  const messages = activeSession?.messages ?? [];
  const messagesLoading = activeSession?.messages === null;

  // ── Helpers ────────────────────────────────────────────────────────────────
  function updateSession(id, updater) {
    setSessions(prev => prev.map(s => s.id === id ? { ...s, ...updater(s) } : s));
  }

  function appendMessage(sessionId, msg) {
    updateSession(sessionId, s => ({ messages: [...(s.messages ?? []), msg] }));
  }

  // ── New chat ───────────────────────────────────────────────────────────────
  const handleNewChat = useCallback(async () => {
    try {
      const id = await createSession();
      const session = makeSession(id);
      setSessions(prev => [session, ...prev]);
      setActiveId(id);
      setActiveSession(id);
      setInput("");
      setError(null);
      setCurrentPlan(null);
      setAutoMode(false);
    } catch (e) {
      console.error("Failed to create session:", e);
    }
  }, []);

  // ── Switch session ─────────────────────────────────────────────────────────
  async function handleSelectSession(id) {
    setActiveId(id);
    setActiveSession(id);
    setError(null);
    setCurrentPlan(null);
    // Load messages for sessions that were restored from the server (messages: null)
    const session = sessions.find(s => s.id === id);
    if (session && session.messages === null) {
      try {
        const msgs = await getSessionMessages(id);
        setSessions(prev => prev.map(s => s.id === id ? { ...s, messages: msgs } : s));
      } catch {
        setSessions(prev => prev.map(s => s.id === id ? { ...s, messages: [] } : s));
      }
    }
  }

  // ── Load persisted sessions on mount; create one if none exist ────────────
  useEffect(() => {
    (async () => {
      try {
        const existing = await getSessions();
        if (existing.length > 0) {
          // Restore session list with empty messages — load on demand when selected
          _sessionCounter = existing.length;
          const restored = existing.map(s => ({ id: s.id, title: s.title, messages: null }));
          setSessions(restored);
          const first = restored[0];
          setActiveId(first.id);
          setActiveSession(first.id);
          // Load messages for the most recent session
          const msgs = await getSessionMessages(first.id);
          setSessions(prev => prev.map(s => s.id === first.id ? { ...s, messages: msgs } : s));
        } else {
          await handleNewChat();
        }
      } catch {
        await handleNewChat();
      }
    })();
  }, []);

  // ── Auto-scroll ────────────────────────────────────────────────────────────
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, thinking]);
  useEffect(() => { inputRef.current?.focus(); }, [activeId]);

  // ── Hooks ──────────────────────────────────────────────────────────────────
  const { recording, transcribing, toggle: toggleVoice } = useVoice({
    canvasRef,
    onTranscript: (text) => {
      setInput(prev => prev ? prev + " " + text : text);
      inputRef.current?.focus();
    },
  });

  useFileDrop({
    onDragging: setDragging,
    onFile:     (att) => { setAttachments(prev => [...prev, att]); inputRef.current?.focus(); },
    onError:    setError,
  });

  useKeyboardShortcuts([
    {
      combo: ["ctrlKey", "l"],
      handler: () => { setAutoMode(p => !p); setCurrentPlan(null); },
      deps: [],
    },
    {
      combo: ["ctrlKey", "h"],
      handler: () => setSidebarOpen(p => !p),
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
    if ((!text && !attachments.length) || thinking || !activeId || messagesLoading) return;

    setInput("");
    if (inputRef.current) inputRef.current.style.height = "auto";
    setError(null);

    // Auto-title session from first message
    if (messages.length === 0 && text) {
      const title = text.length > 40 ? text.slice(0, 40) + "…" : text;
      updateSession(activeId, () => ({ title }));
    }

    if (autoMode && text) {
      setAttachments([]);
      appendMessage(activeId, { role: "user", content: `[AUTO] ${text}` });
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
            const failed  = event?.plan?.steps?.filter(s => s.status === "failed") ?? [];
            const summary = event?.plan?.status === "completed"
              ? `Autonomous task completed${failed.length ? ` (${failed.length} step(s) failed)` : ""}.`
              : "Autonomous task stopped.";
            appendMessage(activeId, { role: "assistant", content: summary });
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
    appendMessage(activeId, {
      role: "user",
      content: text || "(image)",
      previews: sentAttachments.map(a => a.preview),
    });
    setThinking(true);

    const currentSessionId = activeId;
    const tryFetch = async () => {
      try {
        const { response: reply, tools_used, agents_trace, file_url } =
          await sendMessage(text || "(describe this image)", sentAttachments.map(a => a.file));
        appendMessage(currentSessionId, { role: "assistant", content: reply, tools_used, agents_trace, file_url });
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
    setAttachments(prev => prev.filter((_, i) => i !== index));
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

      <div className="app-body">
        {/* ── Sidebar toggle tab (floating, always visible) ── */}
        <button
          className={`sidebar-toggle-tab${sidebarOpen ? " sidebar-toggle-tab--open" : ""}`}
          onClick={() => setSidebarOpen(p => !p)}
          title="Toggle sidebar (Ctrl+H)"
        >
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            {sidebarOpen
              ? <polyline points="7,1 3,5 7,9" />
              : <polyline points="3,1 7,5 3,9" />}
          </svg>
        </button>

        {/* ── Sidebar ── */}
        <aside className={`sidebar ${sidebarOpen ? "" : "sidebar--closed"}`}>
          <div className="sidebar-top">
            <button className="new-chat-btn" onClick={handleNewChat} title="New chat">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <line x1="6" y1="1" x2="6" y2="11" />
                <line x1="1" y1="6" x2="11" y2="6" />
              </svg>
              New chat
            </button>
          </div>

          <nav className="session-list">
            {sessions.map(s => (
              <button
                key={s.id}
                className={`session-item ${s.id === activeId ? "session-item--active" : ""}`}
                onClick={() => handleSelectSession(s.id)}
                title={s.title}
              >
                <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M1 9.5V2a1 1 0 011-1h7a1 1 0 011 1v5.5a1 1 0 01-1 1H3L1 9.5z" />
                </svg>
                <span className="session-title">{s.title}</span>
              </button>
            ))}
          </nav>
        </aside>

        {/* ── Chat area ── */}
        <div className="chat-wrap">
          <main className="chat">
            {messagesLoading && (
              <div className="empty">
                <div className="empty-glow" />
                <p className="empty-text">Loading…</p>
              </div>
            )}
            {!messagesLoading && messages.length === 0 && !thinking && (
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
                  {m.role === "assistant" && m.file_url && (
                    <button className="file-download" onClick={() => downloadFile(m.file_url)}>
                      <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M6.5 1v7M3.5 5.5l3 3 3-3" /><path d="M1 10h11" />
                      </svg>
                      Download PDF
                    </button>
                  )}
                  {m.role === "assistant" && (m.agents_trace?.length > 0 || m.tools_used?.length > 0) && (
                    <div className="agent-flow">
                      {m.agents_trace?.map((name, idx) => (
                        <span key={idx} className="agent-flow-item">
                          {idx > 0 && <span className="agent-flow-arrow">→</span>}
                          <span className="agent-flow-name">{name}</span>
                        </span>
                      ))}
                      {m.tools_used?.filter(t => !t.startsWith("transfer_to_")).map(t => (
                        <span key={t} className="tool-badge">{t}</span>
                      ))}
                    </div>
                  )}
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
            onAutoToggle={() => { setAutoMode(p => !p); setCurrentPlan(null); }}
            inputRef={inputRef}
          />
        </div>
      </div>
    </div>
  );
}
