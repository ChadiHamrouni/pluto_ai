/**
 * useSessions — manages the list of chat sessions.
 *
 * Responsibilities:
 *  - Load persisted sessions from the backend on mount
 *  - Create new sessions
 *  - Switch the active session (lazy-loads messages on first select)
 *  - Expose helpers to update a session's local state (title, messages)
 */

import { useState, useCallback } from "react";
import {
  createSession,
  setActiveSession,
  getSessions,
  getSessionMessages,
} from "../api";

let _sessionCounter = 0;

function makeSession(id, title = null) {
  _sessionCounter += 1;
  return { id, title: title || `Chat ${_sessionCounter}`, messages: [] };
}

export function useSessions() {
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);

  // ── Helpers ──────────────────────────────────────────────────────────────

  function updateSession(id, updater) {
    setSessions(prev =>
      prev.map(s => (s.id === id ? { ...s, ...updater(s) } : s))
    );
  }

  function appendMessage(sessionId, msg) {
    updateSession(sessionId, s => ({
      messages: [...(s.messages ?? []), msg],
    }));
  }

  // ── Switch to a session, lazy-loading its messages if not yet fetched ────

  const selectSession = useCallback(async (id, currentSessions) => {
    setActiveId(id);
    setActiveSession(id);

    const session = currentSessions.find(s => s.id === id);
    if (session && session.messages === null) {
      try {
        const msgs = await getSessionMessages(id);
        setSessions(prev =>
          prev.map(s => (s.id === id ? { ...s, messages: msgs } : s))
        );
      } catch {
        setSessions(prev =>
          prev.map(s => (s.id === id ? { ...s, messages: [] } : s))
        );
      }
    }
  }, []);

  // ── Create a fresh session ────────────────────────────────────────────────

  const newChat = useCallback(async () => {
    try {
      const id = await createSession();
      const session = makeSession(id);
      setSessions(prev => [session, ...prev]);
      setActiveId(id);
      setActiveSession(id);
      return id;
    } catch (e) {
      console.error("Failed to create session:", e);
      return null;
    }
  }, []);

  // ── Load persisted sessions on mount ─────────────────────────────────────

  const loadSessions = useCallback(async () => {
    try {
      const existing = await getSessions();
      if (existing.length > 0) {
        _sessionCounter = existing.length;
        const restored = existing.map(s => ({
          id: s.id,
          title: s.title,
          messages: null, // loaded on demand
        }));
        setSessions(restored);
        const first = restored[0];
        setActiveId(first.id);
        setActiveSession(first.id);
        // Pre-load the most recent session's messages
        const msgs = await getSessionMessages(first.id);
        setSessions(prev =>
          prev.map(s => (s.id === first.id ? { ...s, messages: msgs } : s))
        );
        return first.id;
      }
    } catch {
      // fall through to create a fresh session
    }
    return null; // caller should call newChat()
  }, []);

  return {
    sessions,
    activeId,
    updateSession,
    appendMessage,
    selectSession,
    newChat,
    loadSessions,
  };
}
