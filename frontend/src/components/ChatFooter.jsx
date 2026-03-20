import StatusLabel from "./StatusLabel";

const TRANSCRIBING_WORDS = [
  "Transcribing", "Listening", "Parsing", "Decoding",
  "Converting", "Reading", "Interpreting",
];

export default function ChatFooter({
  input, onInputChange, onKeyDown, thinking,
  attachments, onRemoveAttachment,
  recording, transcribing, onVoiceToggle, canvasRef,
  autoMode, onAutoToggle,
}) {
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

      <div className="input-row">
        <textarea
          className="msg-input"
          placeholder={placeholder}
          value={input}
          onChange={onInputChange}
          onKeyDown={onKeyDown}
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

      <p className="hint">
        {autoMode
          ? "Ctrl+L to exit autonomous mode · Enter to run plan"
          : "Shift+Enter for newline · Ctrl+L for autonomous mode · Drop image, PDF, or TXT to attach"}
      </p>
    </footer>
  );
}
