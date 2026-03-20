/**
 * App — root layout shell.
 *
 * Owns only:
 *  - Top-level shared state (sidebar, settings, attachments, input, autoMode)
 *  - Session management via useSessions
 *  - Chat send logic via useChat
 *  - Voice, file-drop, and keyboard shortcut hooks
 *  - Layout composition: Header + Sidebar + ChatArea + ChatFooter
 *
 * All feature logic lives in hooks/; all UI pieces live in components/.
 */

import { useState, useRef, useEffect } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { writeFile } from "@tauri-apps/plugin-fs";
import { fetchFile } from "./api";

import { useSessions } from "./hooks/useSessions";
import { useChat } from "./hooks/useChat";
import { useVoice } from "./hooks/useVoice";
import { VADListener } from "./hooks/useVAD";
import { useFileDrop } from "./hooks/useFileDrop";
import { useKeyboardShortcuts } from "./hooks/useKeyboardShortcuts";
import { useTTS } from "./hooks/useTTS";

import Header from "./components/Header";
import Sidebar from "./components/Sidebar";
import ChatArea from "./components/ChatArea";
import ChatFooter from "./components/ChatFooter";
import SettingsPanel from "./components/SettingsPanel";

import "./App.css";

// ── File download (Tauri native save dialog) ─────────────────────────────────

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

// ── Root component ────────────────────────────────────────────────────────────

export default function App() {
  const [sidebarOpen, setSidebarOpen]   = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [input, setInput]               = useState("");
  const [attachments, setAttachments]   = useState([]);
  const [dragging, setDragging]         = useState(false);
  const [autoMode, setAutoMode]         = useState(false);
  const [voiceMode, setVoiceMode]       = useState(false);
  // Keep ref in sync so async TTS onDone always sees the latest value
  useEffect(() => { voiceModeRef.current = voiceMode; }, [voiceMode]);

  const bottomRef      = useRef(null);
  const inputRef       = useRef(null);
  const voiceModeRef   = useRef(false);   // always-current voiceMode for async callbacks
  const toggleVoiceRef = useRef(null);    // set after useVoice, used by TTS onDone

  // ── Sessions ──────────────────────────────────────────────────────────────

  const {
    sessions,
    activeId,
    updateSession,
    appendMessage,
    selectSession,
    newChat,
    loadSessions,
  } = useSessions();

  const activeSession   = sessions.find(s => s.id === activeId) ?? null;
  const messages        = activeSession?.messages ?? [];
  const messagesLoading = activeSession?.messages === null;

  // ── Chat logic ────────────────────────────────────────────────────────────

  const {
    thinking,
    error,
    setError,
    currentPlan,
    setCurrentPlan,
    handleSend,
    handleAutoCancel,
  } = useChat({
    activeId,
    messages,
    appendMessage,
    updateSession,
    onReply: (text) => {
      if (voiceModeRef.current) {
        speak(text, {
          onDone: () => {
            // Auto-restart listening after TTS finishes — only if still in voice mode
            if (voiceModeRef.current) toggleVoiceRef.current?.();
          },
        });
      }
    },
  });

  // ── TTS ───────────────────────────────────────────────────────────────────

  const { speaking, speak, stop: stopTTS } = useTTS();

  // ── Mount: load persisted sessions (or create a fresh one) ────────────────

  useEffect(() => {
    (async () => {
      const firstId = await loadSessions();
      if (!firstId) await newChat();
    })();
  }, []);

  // ── Auto-scroll and input focus ───────────────────────────────────────────

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [activeId]);

  // ── Voice ─────────────────────────────────────────────────────────────────

  const { recording, transcribing, startRecording, stopRecording } = useVoice({
    onSend: (text) => {
      stopTTS();
      handleSend({ text, attachments: [], autoMode: false, inputRef, setInput, setAttachments });
    },
  });
  // toggleVoiceRef used by TTS onDone to restart listening in voice mode
  toggleVoiceRef.current = recording ? stopRecording : startRecording;

  // ── VAD (barge-in) — rendered conditionally so ONNX never loads at startup

  // ── File drop ─────────────────────────────────────────────────────────────

  useFileDrop({
    onDragging: setDragging,
    onFile: (att) => {
      setAttachments(prev => [...prev, att]);
      inputRef.current?.focus();
    },
    onError: setError,
  });

  // ── Keyboard shortcuts ────────────────────────────────────────────────────

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
  ]);

  // ── Handlers passed down to children ─────────────────────────────────────

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

  function handleSelectSession(id) {
    setError(null);
    setCurrentPlan(null);
    selectSession(id, sessions);
  }

  async function handleNewChat() {
    setError(null);
    setCurrentPlan(null);
    setAutoMode(false);
    setInput("");
    await newChat();
  }

  function sendCurrentMessage() {
    if (messagesLoading) return;
    handleSend({
      text: input.trim(),
      attachments,
      autoMode,
      inputRef,
      setInput,
      setAttachments,
    });
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className={`layout ${dragging ? "drag-over" : ""}`}>
      {voiceMode && (
        <VADListener
          speaking={speaking}
          stopTTS={stopTTS}
          startRec={startRecording}
          stopRec={stopRecording}
        />
      )}
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
        <Sidebar
          sessions={sessions}
          activeId={activeId}
          isOpen={sidebarOpen}
          onToggle={() => setSidebarOpen(p => !p)}
          onNewChat={handleNewChat}
          onSelectSession={handleSelectSession}
        />

        <div className="chat-wrap">
          <ChatArea
            messages={messages}
            messagesLoading={messagesLoading}
            thinking={thinking}
            error={error}
            currentPlan={currentPlan}
            onAutoCancel={handleAutoCancel}
            onDownload={downloadFile}
            bottomRef={bottomRef}
            voiceMode={voiceMode}
            recording={recording}
            transcribing={transcribing}
            speaking={speaking}
            onExitVoice={() => { setVoiceMode(false); stopTTS(); }}
          />

          <ChatFooter
            input={input}
            onInputChange={handleInputChange}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendCurrentMessage();
              }
            }}
            thinking={thinking}
            attachments={attachments}
            onRemoveAttachment={removeAttachment}
            autoMode={autoMode}
            onAutoToggle={() => { setAutoMode(p => !p); setCurrentPlan(null); }}
            voiceMode={voiceMode}
            onVoiceModeToggle={() => { setVoiceMode(p => !p); if (speaking) stopTTS(); }}
            speaking={speaking}
            inputRef={inputRef}
          />
        </div>
      </div>
    </div>
  );
}
