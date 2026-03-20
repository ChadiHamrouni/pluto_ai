/**
 * Sidebar — session list and new-chat button.
 *
 * Props:
 *  - sessions       {id, title}[]  — list of sessions to display
 *  - activeId       string         — currently active session id
 *  - isOpen         boolean        — whether the sidebar is visible
 *  - onToggle       ()=>void       — open/close the sidebar
 *  - onNewChat      ()=>void       — create a new session
 *  - onSelectSession (id)=>void    — switch to an existing session
 */

export default function Sidebar({ sessions, activeId, isOpen, onToggle, onNewChat, onSelectSession }) {
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
            <button
              key={s.id}
              className={`session-item ${s.id === activeId ? "session-item--active" : ""}`}
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
          ))}
        </nav>
      </aside>
    </>
  );
}
