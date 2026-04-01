import { useState, useEffect, useRef } from "react";
import "./ChatBubble.css";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { openUrl } from "@tauri-apps/plugin-opener";
import PlanTracker from "../PlanTracker";
import { fetchFile } from "../../api";
import * as pdfjsLib from "pdfjs-dist";
import pdfWorkerUrl from "pdfjs-dist/build/pdf.worker.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfWorkerUrl;

function ExternalLink({ href, children }) {
  const handleClick = (e) => {
    e.preventDefault();
    if (href) openUrl(href);
  };
  return <a href={href} onClick={handleClick}>{children}</a>;
}

const MD_COMPONENTS = { a: ExternalLink };

/** Loads a protected file via authenticated fetch and returns an object URL. */
function useAuthFile(fileUrl) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    if (!fileUrl) return;
    let objectUrl;
    fetchFile(fileUrl)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {});
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [fileUrl]);
  return src;
}

/** Renders the first page of a PDF blob URL onto a canvas as a thumbnail. */
function PdfThumbnail({ src, onClick }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!src || !canvasRef.current) return;
    let cancelled = false;

    pdfjsLib.getDocument(src).promise.then((pdf) => {
      if (cancelled) return;
      return pdf.getPage(1);
    }).then((page) => {
      if (cancelled || !canvasRef.current) return;
      const viewport = page.getViewport({ scale: 1 });
      const canvas = canvasRef.current;
      const scale = 360 / viewport.width;
      const scaled = page.getViewport({ scale });
      canvas.width = scaled.width;
      canvas.height = scaled.height;
      page.render({ canvasContext: canvas.getContext("2d"), viewport: scaled });
    }).catch(() => {});

    return () => { cancelled = true; };
  }, [src]);

  return (
    <canvas
      ref={canvasRef}
      className="pdf-thumbnail"
      onClick={onClick}
      title="Click to view full PDF"
    />
  );
}

/** Fullscreen lightbox — shows an image or a PDF iframe. */
function Lightbox({ src, isPdf, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="lightbox-backdrop" onClick={onClose}>
      <button className="lightbox-close" onClick={onClose} aria-label="Close">✕</button>
      {isPdf ? (
        <iframe
          className="lightbox-pdf"
          src={src}
          title="PDF viewer"
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <img
          className="lightbox-img"
          src={src}
          alt="Full size"
          onClick={(e) => e.stopPropagation()}
        />
      )}
    </div>
  );
}

/**
 * ChatBubble — renders a single chat message (user or assistant).
 *
 * Props:
 *  - message  { role, content, previews?, attachmentNames?, tools_used?, agents_trace?, file_url? }
 *  - onDownload  (fileUrl: string) => void
 */
export default function ChatBubble({ message: m, onDownload }) {
  const [lightbox, setLightbox] = useState(null); // { src, isPdf }

  const isPng = m.role === "assistant" && m.file_url?.endsWith(".png");
  const isPdf = m.file_url?.endsWith(".pdf");
  const diagramSrc = useAuthFile(isPng ? m.file_url : null);
  const pdfSrc     = useAuthFile(isPdf ? m.file_url : null);

  if (m.role === "plan") {
    return <PlanTracker plan={m.plan} />;
  }

  return (
    <>
      <div className={`bubble-row ${m.role}`}>
        <div className="bubble">
          {m.role === "assistant" && <span className="bubble-label">Pluto</span>}

          {m.previews?.map((p, j) => (
            <img
              key={j}
              src={p}
              alt="attachment"
              className="bubble-img"
              onClick={() => setLightbox({ src: p, isPdf: false })}
            />
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
            <>
              {isPng && diagramSrc && (
                <img
                  src={diagramSrc}
                  alt="Generated diagram"
                  className="diagram-preview"
                  onClick={() => setLightbox({ src: diagramSrc, isPdf: false })}
                />
              )}
              {isPdf && pdfSrc && (
                <PdfThumbnail
                  src={pdfSrc}
                  onClick={() => setLightbox({ src: pdfSrc, isPdf: true })}
                />
              )}
              <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                <button
                  className="file-download"
                  onClick={() => setLightbox({ src: isPdf ? pdfSrc : diagramSrc, isPdf })}
                >
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M1.5 1h5.586L10 3.914V14.5a.5.5 0 0 1-.5.5h-8a.5.5 0 0 1-.5-.5v-13a.5.5 0 0 1 .5-.5zm4 1H2v12h7V4.5h-3a.5.5 0 0 1-.5-.5V2zm3 .5V4h1.586L8.5 2.5z"/>
                  </svg>
                  {isPng ? "View Diagram" : "View PDF"}
                </button>
                <button className="file-download" onClick={() => onDownload(m.file_url)}>
                  <svg
                    width="13" height="13" viewBox="0 0 13 13"
                    fill="none" stroke="currentColor" strokeWidth="1.5"
                    strokeLinecap="round" strokeLinejoin="round"
                  >
                    <path d="M6.5 1v7M3.5 5.5l3 3 3-3" />
                    <path d="M1 10h11" />
                  </svg>
                  Download
                </button>
              </div>
            </>
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

      {lightbox && (
        <Lightbox
          src={lightbox.src}
          isPdf={lightbox.isPdf}
          onClose={() => setLightbox(null)}
        />
      )}
    </>
  );
}
