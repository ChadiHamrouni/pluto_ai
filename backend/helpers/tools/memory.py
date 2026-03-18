"""Helper functions for memory persistence — ChatGPT-style flat fact store."""

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
    """Insert a memory fact into the DB. Returns the new entry id."""
    conn = sync_db_connection(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO memories (content, category, tags, created_at) VALUES (?, ?, ?, ?)",
        (content, category, tags_json, datetime.utcnow().isoformat()),
    )
    conn.commit()
    entry_id = cursor.lastrowid
    conn.close()
    return entry_id


def load_all_memories(db_path: str, category: str = "") -> list[dict]:
    """Load all stored memory facts, optionally filtered by category."""
    conn = sync_db_connection(db_path)
    if category:
        rows = conn.execute(
            "SELECT id, content, category, tags, created_at FROM memories WHERE category = ? ORDER BY created_at ASC",
            (category,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, content, category, tags, created_at FROM memories ORDER BY created_at ASC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_memory_by_id(db_path: str, memory_id: int) -> bool:
    """Delete a single memory by id. Returns True if a row was deleted."""
    conn = sync_db_connection(db_path)
    cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
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
