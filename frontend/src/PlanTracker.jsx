import "./PlanTracker.css";

const STATUS_ICON = {
  pending: "○",
  in_progress: "◉",
  completed: "✓",
  failed: "✗",
  skipped: "–",
};

const STATUS_CLASS = {
  pending: "pt-step--pending",
  in_progress: "pt-step--running",
  completed: "pt-step--done",
  failed: "pt-step--failed",
  skipped: "pt-step--skipped",
};

export default function PlanTracker({ plan, onCancel }) {
  if (!plan) return null;

  const { task, steps, status } = plan;
  const isDone = status === "completed" || status === "completed_with_failures" || status === "failed" || status === "paused";

  return (
    <div className="pt-container">
      <div className="pt-header">
        <span className="pt-label">AUTO</span>
        <span className="pt-task">{task}</span>
        <span className={`pt-status pt-status--${status}`}>{status}</span>
      </div>

      <div className="pt-steps">
        {status === "planning" && (
          <div className="pt-planning">Planning…</div>
        )}
        {steps.map((step) => (
          <div key={step.id} className={`pt-step ${STATUS_CLASS[step.status] || ""}`}>
            <span className="pt-step-icon">{STATUS_ICON[step.status] || "○"}</span>
            <div className="pt-step-body">
              <span className="pt-step-desc">{step.description}</span>
              {step.result && (
                <span className="pt-step-result">{step.result}</span>
              )}
              {step.error && (
                <span className="pt-step-error">{step.error}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {!isDone && (
        <button className="pt-cancel" onClick={onCancel}>
          Cancel
        </button>
      )}
    </div>
  );
}
