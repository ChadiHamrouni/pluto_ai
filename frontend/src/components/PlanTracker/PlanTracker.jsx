import { useState } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import "./PlanTracker.css";

const STATUS_CLASS = {
  pending: "pt-step--pending",
  in_progress: "pt-step--running",
  completed: "pt-step--done",
  failed: "pt-step--failed",
  skipped: "pt-step--skipped",
};

export default function PlanTracker({ plan }) {
  const { task, steps, status } = plan;
  const isDone = status === "completed" || status === "completed_with_failures" || status === "failed" || status === "paused";

  const [collapsed, setCollapsed] = useState(isDone);

  return (
    <div className={`pt-container${isDone ? " pt-container--done" : ""}`}>
      <div className="pt-header" onClick={() => setCollapsed(c => !c)} role="button">
        <span className="pt-label">AUTO</span>
        <span className="pt-task">{task}</span>
        <span className={`pt-status pt-status--${status}`}>{status}</span>
        <span className="pt-chevron">{collapsed ? "›" : "⌄"}</span>
      </div>

      {!collapsed && (
        <>
          <div className="pt-steps">
            {status === "planning" && (
              <div className="pt-planning">Planning…</div>
            )}
            {steps.map((step) => {
              const urls = (step.links || []).filter(l => !l.startsWith("search:"));
              return (
                <div key={step.id} className={`pt-step ${STATUS_CLASS[step.status] || ""}`}>
                  <span className="pt-step-dot" />
                  <div className="pt-step-body">
                    <span className="pt-step-desc">{step.description}</span>
                    {urls.length > 0 && (
                      <div className="pt-step-links">
                        {urls.map((url, i) => {
                          let label;
                          try { label = new URL(url).hostname.replace(/^www\./, ""); } catch { label = url; }
                          return (
                            <a key={i} className="pt-link-chip" href={url} onClick={e => { e.preventDefault(); e.stopPropagation(); openUrl(url); }} title={url}>
                              <svg width="9" height="9" viewBox="0 0 16 16" fill="currentColor"><path d="M4.715 6.542 3.343 7.914a3 3 0 1 0 4.243 4.243l1.828-1.829A3 3 0 0 0 8.586 5.5L8 6.086a1.002 1.002 0 0 0-.154.199 2 2 0 0 1 .861 3.337L6.88 11.45a2 2 0 1 1-2.83-2.83l.793-.792a4.018 4.018 0 0 1-.128-1.287z"/><path d="M6.586 4.672A3 3 0 0 0 7.414 9.5l.775-.776a2 2 0 0 1-.896-3.346L9.12 3.55a2 2 0 1 1 2.83 2.83l-.793.792c.112.42.155.855.128 1.287l1.372-1.372a3 3 0 1 0-4.243-4.243z"/></svg>
                              {label}
                            </a>
                          );
                        })}
                      </div>
                    )}
                    {step.error && (
                      <span className="pt-step-error">{step.error}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

        </>
      )}
    </div>
  );
}
