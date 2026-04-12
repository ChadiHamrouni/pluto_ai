/**
 * App — root layout shell.
 *
 * Owns only:
 *  - Top-level shared state (sidebar, settings, attachments, input)
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

import { useAuth } from "./hooks/useAuth";
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
import LoginPage from "./components/LoginPage/LoginPage";

import "./App.css";

async function downloadFile(fileUrl) {
  try {
    const filename = fileUrl.split("/").pop();
    const isPng = filename.endsWith(".png");
    const savePath = await save({
      defaultPath: filename,
      filters: isPng
        ? [{ name: "PNG Image", extensions: ["png"] }]
        : [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (!savePath) return;
    const blob = await fetchFile(fileUrl);
    const buffer = await blob.arrayBuffer();
    await writeFile(savePath, new Uint8Array(buffer));
  } catch (e) {
    console.error("Download failed:", e);
  }
}

export default function App() {
  const { isLoggedIn, loading: authLoading, error: authError, login, logout } = useAuth();

  if (!isLoggedIn) {
    return (
      <div className="layout">
        <Header />
        <LoginPage onLogin={login} loading={authLoading} error={authError} />
      </div>
    );
  }

  return <AppShell onLogout={logout} />;
}

function AppShell({ onLogout }) {
  const [sidebarOpen, setSidebarOpen]   = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [input, setInput]               = useState("");
  const [attachments, setAttachments]   = useState([]);
  const [dragging, setDragging]         = useState(false);
  const [voiceMode, setVoiceMode]       = useState(false);
  useEffect(() => { voiceModeRef.current = voiceMode; }, [voiceMode]);

  const bottomRef      = useRef(null);
  const inputRef       = useRef(null);
  const voiceModeRef   = useRef(false);
  const toggleVoiceRef = useRef(null);

  const {
    sessions,
    activeId,
    updateSession,
    appendMessage,
    appendDelta,
    finalizeLastMessage,
    selectSession,
    newChat,
    loadSessions,
    deleteSession,
  } = useSessions();

  const activeSession   = sessions.find(s => s.id === activeId) ?? null;
  const messages        = activeSession?.messages ?? [];
  const messagesLoading = activeSession?.messages === null;

  const {
    thinking,
    error,
    setError,
    handleSend,
    handleEscape,
  } = useChat({
    activeId,
    messages,
    appendMessage,
    appendDelta,
    finalizeLastMessage,
    updateSession,
    onReply: (text) => {
      if (voiceModeRef.current) {
        speak(text, {
          onDone: () => {
            if (voiceModeRef.current) toggleVoiceRef.current?.();
          },
        });
      }
    },
  });

  const { speaking, speak, stop: stopTTS } = useTTS();

  useEffect(() => {
    (async () => {
      const firstId = await loadSessions();
      if (!firstId) await newChat();
    })();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  useEffect(() => {
    inputRef.current?.focus();
  }, [activeId]);

  const { recording, transcribing, lastTranscript, startRecording, stopRecording } = useVoice({
    onSend: (text) => {
      stopTTS();
      handleSend({ text, attachments: [], inputRef, setInput, setAttachments });
    },
  });
  toggleVoiceRef.current = recording ? stopRecording : startRecording;

  useFileDrop({
    onDragging: setDragging,
    onFile: (att) => {
      setAttachments(prev => [...prev, att]);
      inputRef.current?.focus();
    },
    onError: setError,
  });

  useKeyboardShortcuts([
    {
      combo: ["ctrlKey", "h"],
      handler: () => setSidebarOpen(p => !p),
      deps: [],
    },
    {
      combo: ["Escape"],
      handler: handleEscape,
      condition: thinking,
      deps: [thinking],
    },
  ]);

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
    selectSession(id, sessions);
  }

  async function handleNewChat() {
    setError(null);
    setInput("");
    await newChat();
  }

  async function handleDeleteSession(id) {
    await deleteSession(id, activeId, handleNewChat);
  }

  function sendCurrentMessage() {
    if (messagesLoading) return;
    handleSend({
      text: input.trim(),
      attachments,
      inputRef,
      setInput,
      setAttachments,
    });
  }

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

      <Header onSettings={() => setShowSettings(true)} onLogout={onLogout} />
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}

      <div className="app-body">
        <Sidebar
          sessions={sessions}
          activeId={activeId}
          isOpen={sidebarOpen}
          onToggle={() => setSidebarOpen(p => !p)}
          onNewChat={handleNewChat}
          onSelectSession={handleSelectSession}
          onDeleteSession={handleDeleteSession}
        />

        <div className="chat-wrap">
          <ChatArea
            messages={messages}
            messagesLoading={messagesLoading}
            thinking={thinking}
            error={error}
            onDownload={downloadFile}
            bottomRef={bottomRef}
            voiceMode={voiceMode}
            recording={recording}
            transcribing={transcribing}
            speaking={speaking}
            lastTranscript={lastTranscript}
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
