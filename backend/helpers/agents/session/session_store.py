"""Server-side conversation session store — SQLite-backed.

Sessions and their conversation history are persisted to the same SQLite
database used by memories and notes, so they survive backend restarts.

All public functions are async and use aiosqlite via get_db_connection().
"""

from __future__ import annotations

import json
import uuid

from helpers.core.config_loader import load_config
from helpers.core.db import get_db_connection
from helpers.core.logger import get_logger

logger = get_logger(__name__)


def _db_path() -> str:
    return load_config()["memory"]["db_path"]


async def new_session() -> str:
    """Create a new session in the DB and return its ID."""
    sid = str(uuid.uuid4())
    async with get_db_connection(_db_path()) as db:
        await db.execute(
            "INSERT INTO sessions (id, title) VALUES (?, ?)",
            (sid, "New Chat"),
        )
        await db.commit()
    logger.debug("New session created: %s", sid)
    return sid


async def session_exists(session_id: str) -> bool:
    """Return True if the session ID exists in the DB."""
    async with get_db_connection(_db_path()) as db:
        cur = await db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
        row = await cur.fetchone()
    return row is not None


async def get_history(session_id: str, max_turns: int) -> list[dict]:
    """Return the last max_turns×2 messages for the session (oldest first).
    Only role+content are needed for agent context — metadata is UI-only."""
    limit = max_turns * 2
    async with get_db_connection(_db_path()) as db:
        cur = await db.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content
                FROM conversations
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
            """,
            (session_id, limit),
        )
        rows = await cur.fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


async def append_turn(
    session_id: str,
    user_content: str,
    assistant_content: str,
    assistant_metadata: dict | None = None,
    user_metadata: dict | None = None,
) -> None:
    """Persist a completed user/assistant exchange.

    user_metadata may contain:
      - attachment_names: list[str]  — filenames the user attached
      - previews: list[str]          — data-URL previews for images (optional)

    assistant_metadata may contain:
      - tools_used, agents_trace, file_url
    """
    asst_meta_json = json.dumps(assistant_metadata or {})
    user_meta_json = json.dumps(user_metadata or {})
    async with get_db_connection(_db_path()) as db:
        # Auto-create session row if it somehow doesn't exist
        await db.execute(
            "INSERT OR IGNORE INTO sessions (id, title) VALUES (?, ?)",
            (session_id, "New Chat"),
        )
        await db.execute(
            "INSERT INTO conversations (session_id, role, content, metadata, user_metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, "user", user_content, "{}", user_meta_json),
        )
        await db.execute(
            "INSERT INTO conversations (session_id, role, content, metadata) VALUES (?, ?, ?, ?)",
            (session_id, "assistant", assistant_content, asst_meta_json),
        )
        await db.commit()


async def update_session_title(session_id: str, title: str) -> None:
    """Update the display title for a session."""
    async with get_db_connection(_db_path()) as db:
        await db.execute(
            "UPDATE sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        await db.commit()


async def list_sessions() -> list[dict]:
    """Return all sessions ordered newest first.

    Each entry: {id, title, created_at}
    """
    async with get_db_connection(_db_path()) as db:
        cur = await db.execute(
            "SELECT id, title, created_at FROM sessions ORDER BY created_at DESC"
        )
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_session_messages(session_id: str) -> list[dict]:
    """Return the full conversation for a session, oldest first.

    Each entry: {role, content, ...metadata fields}
    - assistant turns include: tools_used, agents_trace, file_url
    - user turns include: attachment_names (list of filenames the user sent)
    """
    async with get_db_connection(_db_path()) as db:
        cur = await db.execute(
            "SELECT role, content, metadata, user_metadata "
            "FROM conversations "
            "WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        )
        rows = await cur.fetchall()

    result = []
    for r in rows:
        msg: dict = {"role": r["role"], "content": r["content"]}
        if r["role"] == "assistant":
            try:
                meta = json.loads(r["metadata"] or "{}")
            except Exception:
                meta = {}
            if meta:
                msg.update(meta)
        else:
            try:
                user_meta = json.loads(r["user_metadata"] or "{}")
            except Exception:
                user_meta = {}
            if user_meta:
                # Use the clean display text if stored; the full extraction
                # is kept in content for agent context only.
                display = user_meta.pop("display_content", None)
                if display is not None:
                    msg["content"] = display
                msg.update(user_meta)
        result.append(msg)
    return result


async def delete_session(session_id: str) -> None:
    """Delete a session and all its messages (CASCADE handles conversations)."""
    async with get_db_connection(_db_path()) as db:
        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
    logger.debug("Session deleted: %s", session_id)


async def clear_session(session_id: str) -> None:
    """Delete all messages for a session without removing the session itself."""
    async with get_db_connection(_db_path()) as db:
        await db.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        await db.commit()
