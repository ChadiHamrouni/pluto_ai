/**
 * ChatBubble — renders a single chat message (user or assistant).
 *
 * Props:
 *  - message  { role, content, previews?, tools_used?, agents_trace?, file_url? }
 *  - onDownload  (fileUrl: string) => void  — called when the user clicks Download PDF
 */

export default function ChatBubble({ message: m, onDownload }) {
  return (
    <div className={`bubble-row ${m.role}`}>
      <div className="bubble">
        {m.role === "assistant" && <span className="bubble-label">Jarvis</span>}

        {m.previews?.map((p, j) => (
          <img key={j} src={p} alt="attachment" className="bubble-img" />
        ))}

        {m.content !== "(image)" && <p className="bubble-text">{m.content}</p>}

        {m.role === "assistant" && m.file_url && (
          <button className="file-download" onClick={() => onDownload(m.file_url)}>
            <svg
              width="13" height="13" viewBox="0 0 13 13"
              fill="none" stroke="currentColor" strokeWidth="1.5"
              strokeLinecap="round" strokeLinejoin="round"
            >
              <path d="M6.5 1v7M3.5 5.5l3 3 3-3" />
              <path d="M1 10h11" />
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
            {m.tools_used
              ?.filter(t => !t.startsWith("transfer_to_"))
              .map(t => (
                <span key={t} className="tool-badge">{t}</span>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
