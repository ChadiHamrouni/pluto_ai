import "./ChatBubble.css";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { openUrl } from "@tauri-apps/plugin-opener";
import PlanTracker from "../PlanTracker";

function ExternalLink({ href, children }) {
  const handleClick = (e) => {
    e.preventDefault();
    if (href) openUrl(href);
  };
  return <a href={href} onClick={handleClick}>{children}</a>;
}

const MD_COMPONENTS = { a: ExternalLink };

/**
 * ChatBubble — renders a single chat message (user or assistant).
 *
 * Props:
 *  - message  { role, content, previews?, tools_used?, agents_trace?, file_url? }
 *  - onDownload  (fileUrl: string) => void  — called when the user clicks Download PDF
 */

export default function ChatBubble({ message: m, onDownload }) {
  if (m.role === "plan") {
    return <PlanTracker plan={m.plan} />;
  }

  return (
    <div className={`bubble-row ${m.role}`}>
      <div className="bubble">
        {m.role === "assistant" && <span className="bubble-label">Pluto</span>}

        {m.previews?.map((p, j) => (
          <img key={j} src={p} alt="attachment" className="bubble-img" />
        ))}

        {m.attachmentNames?.map((name, j) => (
          <div key={j} className="bubble-file-pill">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
              <path d="M4 0a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V5.5L9.5 0H4zm5 1v4h4L9 1zM5.5 8h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1 0-1zm0 2h5a.5.5 0 0 1 0 1h-5a.5.5 0 0 1 0-1zm0 2h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1 0-1z"/>
            </svg>
            <span>{name}</span>
          </div>
        ))}

        {m.content !== "(image)" && (
          m.role === "assistant" ? (
            <div className="bubble-text bubble-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>{m.content}</ReactMarkdown>
            </div>
          ) : (
            <p className="bubble-text">{m.content}</p>
          )
        )}

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

        {m.role === "assistant" && (m.agents_trace?.length > 0 || m.tools_used?.length > 0 || m.tokens_per_second) && (
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
            {m.tokens_per_second && (
              <span className="tok-speed">{m.tokens_per_second} tok/s</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
