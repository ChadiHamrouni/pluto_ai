import { getCurrentWindow } from "@tauri-apps/api/window";
import { open } from "@tauri-apps/plugin-dialog";
import { useState, useEffect } from "react";
import { getVaultPath, setVaultPath } from "../../api";
import "./Header.css";

export default function Header({ autoMode, onSettings, onLogout }) {
  const [expanded, setExpanded] = useState(false);
  const [vault, setVault] = useState("");

  useEffect(() => {
    getVaultPath().then(setVault).catch(() => {});
  }, []);

  async function handlePickVault() {
    const selected = await open({ directory: true, title: "Select Obsidian Vault" });
    if (selected) {
      await setVaultPath(selected);
      setVault(selected);
    }
  }

  async function handleExpand() {
    const win = getCurrentWindow();
    await win.toggleMaximize();
    setExpanded(await win.isMaximized());
  }

  async function handleClose() {
    await getCurrentWindow().close();
  }

  // Show just the folder name from the full path
  const vaultLabel = vault ? vault.split(/[/\\]/).filter(Boolean).pop() : "";

  return (
    <header className="header" data-tauri-drag-region>
      <div className="header-left" data-tauri-drag-region>
        <span className="header-title" data-tauri-drag-region>PLUTO</span>
        <span className="header-sub" data-tauri-drag-region>
          {autoMode ? "autonomous mode" : "personal assistant"}
        </span>
        {autoMode && (
          <span className="header-auto-badge" data-tauri-drag-region>AUTO</span>
        )}
      </div>
      <div className="header-actions">
        <button
          className="expand-btn vault-btn"
          onClick={handlePickVault}
          title={vault ? `Vault: ${vault}` : "Set Obsidian vault"}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M13 11a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1h3.5l2 2H12a1 1 0 0 1 1 1v6z" />
          </svg>
          {vaultLabel && <span className="vault-label">{vaultLabel}</span>}
        </button>
        {onLogout && (
          <button className="expand-btn" onClick={onLogout} title="Sign out">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 2H2a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h3" />
              <polyline points="10 10 13 7 10 4" />
              <line x1="13" y1="7" x2="5" y2="7" />
            </svg>
          </button>
        )}
        <button className="expand-btn" onClick={onSettings} title="Model settings">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="7" cy="7" r="2" />
            <path d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.93 2.93l1.06 1.06M10.01 10.01l1.06 1.06M2.93 11.07l1.06-1.06M10.01 3.99l1.06-1.06" />
          </svg>
        </button>
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
