import { useState, useEffect } from "react";
import StatusLabel from "./StatusLabel";
import SlashMenu, { COMMANDS } from "./SlashMenu";

const TRANSCRIBING_WORDS = [
  "Transcribing", "Listening", "Parsing", "Decoding",
  "Converting", "Reading", "Interpreting",
];

export default function ChatFooter({
  input, onInputChange, onKeyDown, thinking,
  attachments, onRemoveAttachment,
  recording, transcribing, onVoiceToggle, canvasRef,
  autoMode, onAutoToggle,
  inputRef,
}) {
  const [slashIndex, setSlashIndex] = useState(0);

  // Detect slash command prefix in input
  const slashQuery = (() => {
    const trimmed = input.trimStart();
    if (!trimmed.startsWith("/")) return null;
    const word = trimmed.split(/\s/)[0];
    if (trimmed === word) return word;
    return null;
  })();

  const slashFiltered = slashQuery === "/"
    ? COMMANDS
    : slashQuery
      ? COMMANDS.filter((c) => c.cmd.startsWith(slashQuery))
      : [];

  // Reset index when menu appears or filter changes
  useEffect(() => { setSlashIndex(0); }, [slashQuery]);

  function handleSlashSelect(cmd) {
    const rest = input.trimStart().replace(/^\/\S*/, "").trimStart();
    const next = rest ? `${cmd} ${rest}` : `${cmd} `;
    onInputChange({ target: { value: next } });
    inputRef?.current?.focus();
  }

  function handleKeyDown(e) {
    if (slashQuery && slashFiltered.length) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSlashIndex((i) => (i + 1) % slashFiltered.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSlashIndex((i) => (i - 1 + slashFiltered.length) % slashFiltered.length);
        return;
      }
      if (e.key === "Tab" || e.key === "Enter") {
        e.preventDefault();
        handleSlashSelect(slashFiltered[slashIndex].cmd);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        onInputChange({ target: { value: "" } });
        return;
      }
    }
    onKeyDown(e);
  }

  const placeholder = autoMode
    ? "Describe a multi-step task for Jarvis to plan and execute…"
    : attachments.length
      ? "Add a message… (or just Enter)"
      : "Message Jarvis…";

  return (
    <footer className="footer">
      {attachments.length > 0 && (
        <div className="attachment-bar">
          {attachments.map((a, i) => (
            <div key={i} className="attachment-item">
              {a.isPdf
                ? <span className="attachment-pdf-icon">{a.fileExt?.toUpperCase() || "FILE"}</span>
                : <img src={a.preview} alt="attachment preview" className="attachment-thumb" />
              }
              <span className="attachment-name">{a.file.name}</span>
              <button className="attachment-remove" onClick={() => onRemoveAttachment(i)}>✕</button>
            </div>
          ))}
        </div>
      )}

      {recording && (
        <div className="wave-container">
          <canvas ref={canvasRef} className="wave-canvas" width={340} height={48} />
        </div>
      )}

      {transcribing && (
        <div className="transcribing-row">
          <StatusLabel words={TRANSCRIBING_WORDS} />
        </div>
      )}

      <div className="input-wrap">
        {slashQuery && (
          <SlashMenu
            query={slashQuery}
            activeIndex={slashIndex}
            onSelect={handleSlashSelect}
          />
        )}
        <div className="input-row">
          <textarea
            ref={inputRef}
            className="msg-input"
            placeholder={placeholder}
            value={input}
            onChange={onInputChange}
            onKeyDown={handleKeyDown}
            disabled={thinking}
          />
          <div className="mic-stack">
            <button
              className={`auto-toggle ${autoMode ? "auto-toggle--on" : ""}`}
              onClick={onAutoToggle}
              title={autoMode ? "Autonomous mode ON — click to disable" : "Click to enable autonomous mode"}
            >
              AUTO
            </button>
            <button
              className={`voice-btn ${recording ? "recording" : ""}`}
              onClick={onVoiceToggle}
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
      </div>

      <p className="hint">
        {autoMode
          ? "Ctrl+L to exit autonomous mode · Enter to run plan"
          : "Shift+Enter for newline · Ctrl+H for history · Ctrl+L for autonomous mode · Drop to attach"}
      </p>
    </footer>
  );
}
