import React, { useState, useRef, useEffect } from "react";
import { sendMessage } from "./api";
import "./App.css";

export default function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  const history = messages.map((m) => ({
    role: m.role,
    content: m.content,
  }));

  async function handleSend() {
    const text = input.trim();
    if (!text || thinking) return;

    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setThinking(true);

    try {
      const reply = await sendMessage(text, history);
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

  return (
    <div className="layout">
      {/* Header */}
      <header className="header">
        <span className="header-title">PERSONAL AI</span>
        <span className="header-sub">assistant</span>
      </header>

      {/* Chat */}
      <main className="chat">
        {messages.length === 0 && !thinking && (
          <div className="empty">
            <div className="empty-glow" />
            <p className="empty-text">How can I help you today?</p>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`bubble-row ${m.role}`}>
            <div className="bubble">
              <span className="bubble-label">{m.role === "user" ? "You" : "AI"}</span>
              <p className="bubble-text">{m.content}</p>
            </div>
          </div>
        ))}

        {thinking && (
          <div className="bubble-row assistant">
            <div className="bubble thinking">
              <span className="bubble-label">AI</span>
              <span className="dots"><span /><span /><span /></span>
            </div>
          </div>
        )}

        {error && (
          <div className="error-row">
            <span>{error}</span>
          </div>
        )}

        <div ref={bottomRef} />
      </main>

      {/* Footer */}
      <footer className="footer">
        <div className="input-row">
          <textarea
            ref={inputRef}
            className="msg-input"
            placeholder="Message your assistant…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            rows={1}
            disabled={thinking}
          />
          <button
            className={`send-btn ${thinking ? "disabled" : ""}`}
            onClick={handleSend}
            disabled={thinking}
          >
            Send
          </button>
        </div>
        <p className="hint">Enter to send · Shift+Enter for newline</p>
      </footer>
    </div>
  );
}