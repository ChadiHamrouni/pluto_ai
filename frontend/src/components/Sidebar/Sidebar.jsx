import "./Sidebar.css";

/**
 * Sidebar — session list and new-chat button.
 *
 * Props:
 *  - sessions         {id, title}[]  — list of sessions to display
 *  - activeId         string         — currently active session id
 *  - isOpen           boolean        — whether the sidebar is visible
 *  - onToggle         ()=>void       — open/close the sidebar
 *  - onNewChat        ()=>void       — create a new session
 *  - onSelectSession  (id)=>void     — switch to an existing session
 *  - onDeleteSession  (id)=>void     — delete a session
 */

export default function Sidebar({ sessions, activeId, isOpen, onToggle, onNewChat, onSelectSession, onDeleteSession }) {
  return (
    <>
      {/* Floating arrow tab — always visible, centered on left edge */}
      <button
        className={`sidebar-toggle-tab${isOpen ? " sidebar-toggle-tab--open" : ""}`}
        onClick={onToggle}
        title="Toggle sidebar (Ctrl+H)"
      >
        <svg
          width="10" height="10" viewBox="0 0 10 10"
          fill="none" stroke="currentColor" strokeWidth="1.8"
          strokeLinecap="round" strokeLinejoin="round"
        >
          {isOpen
            ? <polyline points="7,1 3,5 7,9" />
            : <polyline points="3,1 7,5 3,9" />}
        </svg>
      </button>

      <aside className={`sidebar ${isOpen ? "" : "sidebar--closed"}`}>
        <div className="sidebar-top">
          <button className="new-chat-btn" onClick={onNewChat} title="New chat">
            <svg
              width="12" height="12" viewBox="0 0 12 12"
              fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
            >
              <line x1="6" y1="1" x2="6" y2="11" />
              <line x1="1" y1="6" x2="11" y2="6" />
            </svg>
            New chat
          </button>
        </div>

        <nav className="session-list">
          {sessions.map(s => (
            <div
              key={s.id}
              className={`session-item ${s.id === activeId ? "session-item--active" : ""}`}
            >
              <button
                className="session-item-btn"
                onClick={() => onSelectSession(s.id)}
                title={s.title}
              >
                <svg
                  width="11" height="11" viewBox="0 0 11 11"
                  fill="none" stroke="currentColor" strokeWidth="1.4"
                  strokeLinecap="round" strokeLinejoin="round"
                >
                  <path d="M1 9.5V2a1 1 0 011-1h7a1 1 0 011 1v5.5a1 1 0 01-1 1H3L1 9.5z" />
                </svg>
                <span className="session-title">{s.title}</span>
              </button>
              <button
                className="session-delete-btn"
                onClick={(e) => { e.stopPropagation(); onDeleteSession(s.id); }}
                title="Delete conversation"
              >
                <svg
                  width="11" height="11" viewBox="0 0 11 11"
                  fill="none" stroke="currentColor" strokeWidth="1.5"
                  strokeLinecap="round" strokeLinejoin="round"
                >
                  <polyline points="2,3 9,3" />
                  <path d="M4,3V2h3v1" />
                  <rect x="2.5" y="3" width="6" height="6.5" rx="0.8" />
                  <line x1="4.5" y1="5" x2="4.5" y2="8" />
                  <line x1="6.5" y1="5" x2="6.5" y2="8" />
                </svg>
              </button>
            </div>
          ))}
        </nav>
      </aside>
    </>
  );
}
