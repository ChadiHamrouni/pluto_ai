"""Helper functions for calendar/event persistence."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.obsidian import sync_vault_background

logger = get_logger(__name__)


def get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def create_event(
    db_path: str,
    title: str,
    start_time: str,
    end_time: str | None,
    description: str = "",
    location: str = "",
) -> dict:
    """Insert an event. start_time / end_time must be ISO-8601 strings (UTC)."""
    conn = _connect(db_path)
    cursor = conn.execute(
        """INSERT INTO events (title, start_time, end_time, description, location)
           VALUES (?, ?, ?, ?, ?)""",
        (title, start_time, end_time, description, location),
    )
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info("Created event %d: %s at %s", event_id, title, start_time)
    result = {"id": event_id, "title": title, "start_time": start_time, "end_time": end_time}
    sync_vault_background()
    return result


def list_events(db_path: str, from_time: str, to_time: str) -> list[dict]:
    """Return events whose start_time falls within [from_time, to_time]."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT id, title, start_time, end_time, description, location
           FROM events
           WHERE start_time >= ? AND start_time <= ?
           ORDER BY start_time ASC""",
        (from_time, to_time),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def upcoming_events(db_path: str, hours: int = 24) -> list[dict]:
    """Return events starting within the next *hours* hours."""
    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=hours)
    return list_events(db_path, now.isoformat(), until.isoformat())


def delete_event(db_path: str, event_id: int) -> bool:
    """Delete an event by id. Returns True if a row was removed."""
    conn = _connect(db_path)
    cursor = conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    if deleted:
        sync_vault_background()
    return deleted
