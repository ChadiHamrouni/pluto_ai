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
  deleteSession as apiDeleteSession,
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

  /** Append a delta to the last assistant message's content (for streaming). */
  function appendDelta(sessionId, delta) {
    updateSession(sessionId, s => {
      const msgs = [...(s.messages ?? [])];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, content: (last.content || "") + delta };
      }
      return { messages: msgs };
    });
  }

  /** Replace the last assistant message with final metadata (for stream completion). */
  function finalizeLastMessage(sessionId, updates) {
    updateSession(sessionId, s => {
      const msgs = [...(s.messages ?? [])];
      const last = msgs[msgs.length - 1];
      if (last && last.role === "assistant") {
        msgs[msgs.length - 1] = { ...last, ...updates, streaming: false };
      }
      return { messages: msgs };
    });
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

  // ── Delete a session ─────────────────────────────────────────────────────

  const deleteSession = useCallback(async (id, currentActiveId, onNewChat) => {
    try {
      await apiDeleteSession(id);
    } catch (e) {
      console.error("Failed to delete session:", e);
      return;
    }
    setSessions(prev => {
      const remaining = prev.filter(s => s.id !== id);
      return remaining;
    });
    // If we deleted the active session, switch to another or create a new one
    if (id === currentActiveId) {
      setSessions(prev => {
        const remaining = prev.filter(s => s.id !== id);
        if (remaining.length > 0) {
          const next = remaining[0];
          setActiveId(next.id);
          setActiveSession(next.id);
        } else {
          onNewChat?.();
        }
        return remaining;
      });
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
    appendDelta,
    finalizeLastMessage,
    selectSession,
    newChat,
    loadSessions,
    deleteSession,
  };
}
