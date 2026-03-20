import { getCurrentWindow } from "@tauri-apps/api/window";
import { useState } from "react";

export default function Header({ autoMode }) {
  const [expanded, setExpanded] = useState(false);

  async function handleExpand() {
    const win = getCurrentWindow();
    await win.toggleMaximize();
    setExpanded(await win.isMaximized());
  }

  async function handleClose() {
    await getCurrentWindow().close();
  }

  return (
    <header className="header" data-tauri-drag-region>
      <div className="header-left" data-tauri-drag-region>
        <span className="header-title" data-tauri-drag-region>JARVIS</span>
        <span className="header-sub" data-tauri-drag-region>
          {autoMode ? "autonomous mode" : "personal assistant"}
        </span>
        {autoMode && (
          <span className="header-auto-badge" data-tauri-drag-region>AUTO</span>
        )}
      </div>
      <div className="header-actions">
        <button className="expand-btn" onClick={handleExpand} title={expanded ? "Collapse" : "Expand"}>
          {expanded ? (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <polyline points="9,1 13,1 13,5" /><line x1="8" y1="6" x2="13" y2="1" />
              <polyline points="5,13 1,13 1,9" /><line x1="6" y1="8" x2="1" y2="13" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <polyline points="8,1 13,1 13,6" /><line x1="7" y1="7" x2="13" y2="1" />
              <polyline points="6,13 1,13 1,8" /><line x1="7" y1="7" x2="1" y2="13" />
            </svg>
          )}
        </button>
        <button className="close-btn" onClick={handleClose}>✕</button>
      </div>
    </header>
  );
}
