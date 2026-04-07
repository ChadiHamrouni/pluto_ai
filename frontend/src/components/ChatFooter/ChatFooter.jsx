import { useState, useEffect } from "react";
import SlashMenu from "../SlashMenu";
import { fetchCommands } from "../../api";
import "./ChatFooter.css";

export default function ChatFooter({
  input, onInputChange, onKeyDown, thinking,
  attachments, onRemoveAttachment,
  voiceMode, onVoiceModeToggle, speaking,
  inputRef,
}) {
  const [slashIndex, setSlashIndex] = useState(0);
  const [commands, setCommands] = useState([]);

  useEffect(() => {
    fetchCommands().then(setCommands).catch(() => {});
  }, []);

  // Detect slash command prefix in input
  const slashQuery = (() => {
    const trimmed = input.trimStart();
    if (!trimmed.startsWith("/")) return null;
    const word = trimmed.split(/\s/)[0];
    if (trimmed === word) return word;
    return null;
  })();

  const slashFiltered = slashQuery === "/"
    ? commands
    : slashQuery
      ? commands.filter((c) => c.cmd.startsWith(slashQuery))
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

  const placeholder = attachments.length
    ? "Add a message… (or just Enter)"
    : "Message Pluto…";

  return (
    <footer className="footer">
      {attachments.length > 0 && (
        <div className="attachment-bar">
          {attachments.map((a, i) => (
            <div key={i} className="attachment-item">
              {a.isPdf ? (
                <span className="attachment-pdf-icon">
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M4 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V5.5L9.5 0H4zm5 1v4h4L9 1zM5.5 8h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1 0-1zm0 2h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1 0-1zm0 2h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1 0-1z"/>
                  </svg>
                </span>
              ) : (
                <img src={a.preview} alt="attachment preview" className="attachment-thumb" />
              )}
              <span className="attachment-name">{a.file.name}</span>
              <button className="attachment-remove" onClick={() => onRemoveAttachment(i)}>✕</button>
            </div>
          ))}
        </div>
      )}


      <div className="input-wrap">
        {slashQuery && (
          <SlashMenu
            commands={commands}
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
            {/* VOICE pill */}
            <button
              className={`mode-btn ${voiceMode ? "mode-btn--on" : ""}`}
              onClick={onVoiceModeToggle}
              title={voiceMode ? "Voice mode ON — click to disable" : "Enable voice mode"}
            >
              {speaking ? (
                <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="1" y="4" width="3" height="8" rx="1.5" />
                  <rect x="6" y="1" width="3" height="14" rx="1.5" />
                  <rect x="11" y="4" width="3" height="8" rx="1.5" />
                </svg>
              ) : (
                <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="5" y="1" width="6" height="9" rx="3" />
                  <path d="M2.5 8a5.5 5.5 0 0 0 11 0" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round"/>
                </svg>
              )}
              Voice
            </button>

          </div>
        </div>
      </div>

    </footer>
  );
}
