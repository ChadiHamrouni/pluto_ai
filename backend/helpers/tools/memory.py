"""Helper functions for memory persistence — hybrid search fact store."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)


def get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def sync_db_connection(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def insert_memory(db_path: str, content: str, category: str, tags_json: str) -> int:
    """Insert a memory fact into DB and FTS index. Returns the new entry id."""
    conn = sync_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO memories (content, category, tags, created_at) VALUES (?, ?, ?, ?)",
        (content, category, tags_json, datetime.utcnow().isoformat()),
    )
    entry_id = cursor.lastrowid
    # Keep FTS index in sync
    try:
        cursor.execute(
            "INSERT INTO memories_fts (content, memory_id) VALUES (?, ?)",
            (content, entry_id),
        )
    except Exception as exc:
        logger.warning("FTS insert failed (non-fatal): %s", exc)
    conn.commit()
    conn.close()
    return entry_id


def load_all_memories(db_path: str, category: str = "") -> list[dict]:
    """Load all stored memory facts, optionally filtered by category."""
    conn = sync_db_connection(db_path)
    if category:
        rows = conn.execute(
            "SELECT id, content, category, tags, created_at FROM memories"
            " WHERE category = ? ORDER BY created_at ASC",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, content, category, tags, created_at FROM memories ORDER BY created_at ASC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def search_memories(db_path: str, query: str, top_k: int = 10) -> list[dict]:
    """Search memories using SQLite FTS5 BM25 ranking.

    FTS5 handles term matching, ranking, and stemming natively in the DB engine —
    no Python-side scanning. Falls back to most-recent memories if FTS returns
    nothing or the query is empty.

    Returns at most top_k most relevant memories, ordered by relevance.
    """
    if not query or not query.strip():
        return _most_recent(db_path, top_k)

    conn = sync_db_connection(db_path)

    # FTS5 BM25 search — indexed, log-scale, no Python loop
    fts_ids: list[int] = []
    try:
        rows = conn.execute(
            "SELECT memory_id FROM memories_fts WHERE content MATCH ? ORDER BY rank LIMIT ?",
            (query, top_k),
        ).fetchall()
        fts_ids = [r[0] for r in rows]
    except Exception as exc:
        logger.warning("FTS search failed: %s", exc)

    if not fts_ids:
        conn.close()
        return _most_recent(db_path, top_k)

    placeholders = ",".join("?" * len(fts_ids))
    rows = conn.execute(
        f"SELECT id, content, category, tags, created_at FROM memories"
        f" WHERE id IN ({placeholders})",
        fts_ids,
    ).fetchall()
    conn.close()

    # Preserve FTS relevance order
    id_to_row = {dict(r)["id"]: dict(r) for r in rows}
    return [id_to_row[mid] for mid in fts_ids if mid in id_to_row]


def _most_recent(db_path: str, top_k: int) -> list[dict]:
    """Return the most recently stored memories as a fallback."""
    conn = sync_db_connection(db_path)
    rows = conn.execute(
        "SELECT id, content, category, tags, created_at FROM memories"
        " ORDER BY created_at DESC LIMIT ?",
        (top_k,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_memory_by_id(db_path: str, memory_id: int) -> bool:
    """Delete a single memory by id. Returns True if a row was deleted."""
    conn = sync_db_connection(db_path)
    cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
    try:
        conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (memory_id,))
    except Exception:
        pass
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def delete_old_memories(db_path: str, days: int) -> int:
    """Delete memories older than *days* days. Returns count deleted."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = sync_db_connection(db_path)
    cursor = conn.execute("DELETE FROM memories WHERE created_at < ?", (cutoff,))
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted
