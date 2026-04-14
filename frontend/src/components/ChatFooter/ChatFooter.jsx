import { useState, useEffect } from "react";
import SlashMenu from "../SlashMenu";
import { fetchCommands } from "../../api";
import "./ChatFooter.css";

export default function ChatFooter({
  input, onInputChange, onKeyDown, thinking,
  attachments, onRemoveAttachment,
  recording, transcribing, waveformBars,
  onMicPress, onMicRelease,
  inputRef,
}) {
  const [slashIndex, setSlashIndex] = useState(0);
  const [commands, setCommands] = useState([]);

  useEffect(() => {
    fetchCommands().then(setCommands).catch(() => {});
  }, []);

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

  useEffect(() => { setSlashIndex(0); }, [slashQuery]);

  function handleSlashSelect(cmd) {
    const rest = input.trimStart().replace(/^\/\S*/, "").trimStart();
    const next = rest ? `${cmd} ${rest}` : `${cmd} `;
    onInputChange({ target: { value: next } });
    inputRef?.current?.focus();
  }

  function handleKeyDown(e) {
    if (slashQuery && slashFiltered.length) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSlashIndex((i) => (i + 1) % slashFiltered.length); return; }
      if (e.key === "ArrowUp")   { e.preventDefault(); setSlashIndex((i) => (i - 1 + slashFiltered.length) % slashFiltered.length); return; }
      if (e.key === "Tab" || e.key === "Enter") { e.preventDefault(); handleSlashSelect(slashFiltered[slashIndex].cmd); return; }
      if (e.key === "Escape") { e.preventDefault(); onInputChange({ target: { value: "" } }); return; }
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
          <div className="input-area">
            {/* Waveform — shown above textarea while recording */}
            {(recording || transcribing) && (
              <div className={`waveform-bar-row ${transcribing ? "waveform-bar-row--fading" : ""}`}>
                {waveformBars.map((h, i) => (
                  <div
                    key={i}
                    className="waveform-bar"
                    style={{ "--h": Math.max(0.08, h) }}
                  />
                ))}
              </div>
            )}

            <textarea
              ref={inputRef}
              className={`msg-input ${recording ? "msg-input--recording" : ""}`}
              placeholder={placeholder}
              value={input}
              onChange={onInputChange}
              onKeyDown={handleKeyDown}
              disabled={thinking}
            />
          </div>

          {/* Mic button — hold to dictate */}
          <button
            className={`mic-btn ${recording ? "mic-btn--recording" : transcribing ? "mic-btn--processing" : ""}`}
            onMouseDown={onMicPress}
            onMouseUp={onMicRelease}
            onTouchStart={onMicPress}
            onTouchEnd={onMicRelease}
            title={recording ? "Recording… release to transcribe" : "Hold to dictate"}
            disabled={thinking}
          >
            {recording ? (
              // Stop square icon while recording
              <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                <rect x="3" y="3" width="10" height="10" rx="2" />
              </svg>
            ) : transcribing ? (
              // Spinner dots while transcribing
              <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                <circle cx="3" cy="8" r="1.5" opacity="1" />
                <circle cx="8" cy="8" r="1.5" opacity="0.6" />
                <circle cx="13" cy="8" r="1.5" opacity="0.3" />
              </svg>
            ) : (
              // Mic icon
              <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                <rect x="5" y="1" width="6" height="9" rx="3" />
                <path d="M2.5 8a5.5 5.5 0 0 0 11 0" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round"/>
                <line x1="8" y1="13.5" x2="8" y2="15.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"/>
              </svg>
            )}
          </button>
        </div>
      </div>
    </footer>
  );
}
