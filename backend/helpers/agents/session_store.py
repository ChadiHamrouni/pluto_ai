"""Server-side conversation session store.

Keeps the rolling history on the backend so the frontend only sends the
current message — not the full history on every request. This eliminates
repeated JSON serialisation and HTTP payload growth over long conversations.

Sessions are in-memory (process lifetime). They survive API calls but are
lost on server restart — same as the frontend's React state.
"""

from __future__ import annotations

import uuid
from collections import deque
from typing import Deque

from helpers.core.logger import get_logger

logger = get_logger(__name__)

# session_id → deque of {"role": str, "content": str}
_sessions: dict[str, Deque[dict]] = {}


def new_session() -> str:
    """Create a new session, return its ID."""
    sid = str(uuid.uuid4())
    _sessions[sid] = deque()
    logger.debug("New session: %s", sid)
    return sid


def get_history(session_id: str, max_turns: int) -> list[dict]:
    """Return the last max_turns×2 messages for the session.

    Returns an empty list for unknown session IDs (graceful degradation).
    """
    dq = _sessions.get(session_id)
    if dq is None:
        return []
    limit = max_turns * 2
    return list(dq)[-limit:]


def append_turn(session_id: str, user_content: str, assistant_content: str) -> None:
    """Append a completed user/assistant exchange to the session."""
    dq = _sessions.get(session_id)
    if dq is None:
        dq = deque()
        _sessions[session_id] = dq
    dq.append({"role": "user",      "content": user_content})
    dq.append({"role": "assistant", "content": assistant_content})


def session_exists(session_id: str) -> bool:
    return session_id in _sessions


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)
