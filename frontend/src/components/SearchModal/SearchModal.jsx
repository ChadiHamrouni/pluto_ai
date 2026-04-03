import { useRef, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useContentSearch } from "../../hooks/useContentSearch";
import { useKeyboardShortcuts } from "../../hooks/useKeyboardShortcuts";
import { fetchFile } from "../../api";
import "./SearchModal.css";

const TYPE_ICON = {
  file:     "📄",
  note:     "📝",
  obsidian: "💎",
  image:    "🖼",
};

const TYPE_LABEL = {
  file:     "File",
  note:     "Note",
  obsidian: "Obsidian",
  image:    "Diagram",
};

const FILTER_HINTS = [
  { prefix: "-obsidian", label: "Obsidian" },
  { prefix: "-pdf",      label: "PDFs"     },
  { prefix: "-img",      label: "Diagrams" },
];

export default function SearchModal({ onClose }) {
  const inputRef = useRef(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [lightbox, setLightbox] = useState(null); // { src, isPdf, isMarkdown, mdText, title }
  const [loadingSrc, setLoadingSrc] = useState(null);

  const { query, results, loading, error, handleQueryChange, reset } =
    useContentSearch();

  useEffect(() => {
    inputRef.current?.focus();
    return () => reset();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setActiveIndex(0);
  }, [results]);

  useKeyboardShortcuts([
    {
      combo: ["Escape"],
      handler: () => {
        if (lightbox) {
          setLightbox(null);
        } else {
          onClose();
        }
      },
      deps: [lightbox, onClose],
    },
    {
      combo: ["ArrowDown"],
      handler: () => setActiveIndex(i => Math.min(i + 1, results.length - 1)),
      deps: [results],
    },
    {
      combo: ["ArrowUp"],
      handler: () => setActiveIndex(i => Math.max(i - 1, 0)),
      deps: [],
    },
    {
      combo: ["Enter"],
      handler: () => {
        if (results[activeIndex]) openResult(results[activeIndex]);
      },
      deps: [results, activeIndex],
    },
  ]);

  async function openResult(result) {
    if (!result.file_url) return;
    setLoadingSrc(result.id);
    try {
      const blob = await fetchFile(result.file_url);
      if (result.file_url.endsWith(".md") || result.file_url.endsWith(".txt")) {
        const mdText = await blob.text();
        setLightbox({ src: null, isPdf: false, isMarkdown: true, mdText, title: result.title });
      } else {
        const objectUrl = URL.createObjectURL(blob);
        const isPdf = result.file_url.endsWith(".pdf");
        setLightbox({ src: objectUrl, isPdf, isMarkdown: false, title: result.title });
      }
    } catch (e) {
      console.error("Failed to load file:", e);
    } finally {
      setLoadingSrc(null);
    }
  }

  return (
    <>
      <div className="search-backdrop" onClick={onClose} />

      <div className="search-panel" role="dialog" aria-label="Content search">
        <div className="search-input-row">
          <span className="search-icon">⌕</span>
          <input
            ref={inputRef}
            className="search-input"
            type="text"
            placeholder="Search notes, files, diagrams… or type -note, -pdf, -img"
            value={query}
            onChange={(e) => handleQueryChange(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          {loading && <span className="search-spinner" />}
        </div>

        {!query && (
          <div className="search-hints">
            {FILTER_HINTS.map(h => (
              <button
                key={h.prefix}
                className="search-hint-pill"
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleQueryChange(h.prefix);
                  // Put cursor after prefix + space so user can keep typing
                  setTimeout(() => {
                    const el = inputRef.current;
                    if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
                  }, 0);
                }}
              >
                {h.label}
              </button>
            ))}
          </div>
        )}

        {results.length > 0 && (
          <ul className="search-results">
            {results.map((r, i) => (
              <li
                key={r.id}
                className={[
                  "search-result-item",
                  i === activeIndex ? "search-result-item--active" : "",
                  !r.file_url ? "search-result-item--no-open" : "",
                ].join(" ").trim()}
                onMouseEnter={() => setActiveIndex(i)}
                onMouseDown={(e) => { e.preventDefault(); openResult(r); }}
              >
                <span className="search-result-icon">
                  {TYPE_ICON[r.content_type] ?? "📄"}
                </span>
                <div className="search-result-body">
                  <span className="search-result-title">{r.title}</span>
                  <span className="search-result-snippet">{r.snippet}</span>
                </div>
                <div className="search-result-meta">
                  <span className="search-result-type">
                    {TYPE_LABEL[r.content_type] ?? r.content_type}
                  </span>
                  {loadingSrc === r.id && <span className="search-result-loading">…</span>}
                  {!r.file_url && <span className="search-result-no-preview">no preview</span>}
                </div>
              </li>
            ))}
          </ul>
        )}

        {!loading && query.length >= 2 && results.length === 0 && !error && (
          <div className="search-empty">No results for "{query}"</div>
        )}

        {error && (
          <div className="search-error">Search failed: {error}</div>
        )}

        <div className="search-footer">
          <span>↑↓ navigate</span>
          <span>↵ open</span>
          <span>Esc close</span>
        </div>
      </div>

      {lightbox && (
        <div className="lightbox-backdrop" onClick={() => setLightbox(null)}>
          <button
            className="lightbox-close"
            onClick={() => setLightbox(null)}
            aria-label="Close"
          >✕</button>
          {lightbox.isMarkdown ? (
            <div
              className="search-lightbox-md"
              onClick={(e) => e.stopPropagation()}
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {lightbox.mdText}
              </ReactMarkdown>
            </div>
          ) : lightbox.isPdf ? (
            <iframe
              className="lightbox-pdf"
              src={lightbox.src}
              title={lightbox.title}
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <img
              className="lightbox-img"
              src={lightbox.src}
              alt={lightbox.title}
              onClick={(e) => e.stopPropagation()}
            />
          )}
        </div>
      )}
    </>
  );
}
