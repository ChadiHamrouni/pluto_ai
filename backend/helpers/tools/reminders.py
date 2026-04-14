"""Helper functions for reminder persistence."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

RECURRENCE_DAILY = "daily"
RECURRENCE_WEEKLY = "weekly"
RECURRENCE_MONTHLY = "monthly"


def get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def create_reminder(
    db_path: str,
    title: str,
    remind_at: str,
    recurrence: str = "",
) -> dict:
    """Insert a reminder. remind_at must be ISO-8601 UTC string."""
    conn = _connect(db_path)
    cursor = conn.execute(
        """INSERT INTO reminders (title, remind_at, recurrence)
           VALUES (?, ?, ?)""",
        (title, remind_at, recurrence),
    )
    reminder_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info("Created reminder %d: %s at %s (recurrence=%r)", reminder_id, title, remind_at, recurrence)
    return {"id": reminder_id, "title": title, "remind_at": remind_at, "recurrence": recurrence}


def list_reminders(db_path: str) -> list[dict]:
    """Return all active reminders (not yet permanently deleted)."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT id, title, remind_at, recurrence, notified_at, created_at
           FROM reminders
           ORDER BY remind_at ASC"""
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def delete_reminder(db_path: str, reminder_id: int) -> bool:
    """Delete a reminder by id. Returns True if removed."""
    conn = _connect(db_path)
    cursor = conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted


def _parse_naive_utc(iso: str) -> datetime:
    """Parse any ISO-8601 string to a naive UTC datetime."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None) - dt.utcoffset()
    return dt


def get_due_reminders(db_path: str, window_minutes: int = 15) -> list[dict]:
    """
    Return reminders that are due within the next window_minutes and have not
    been notified yet (or whose recurrence cycle has reset).
    """
    now = datetime.utcnow()  # naive UTC
    until = now + timedelta(minutes=window_minutes)

    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT id, title, remind_at, recurrence, notified_at
           FROM reminders
           ORDER BY remind_at ASC"""
    ).fetchall()
    conn.close()

    due: list[dict] = []
    for row in rows:
        r = _row_to_dict(row)
        try:
            remind_dt = _parse_naive_utc(r["remind_at"])
        except ValueError:
            continue

        recurrence = r.get("recurrence", "")

        if recurrence:
            step = _recurrence_step(recurrence)
            while remind_dt < now - timedelta(minutes=window_minutes):
                remind_dt += step
            if now <= remind_dt <= until:
                notified_at = r.get("notified_at")
                if notified_at:
                    try:
                        notified_dt = _parse_naive_utc(notified_at)
                        if (now - notified_dt) < step:
                            continue
                    except ValueError:
                        pass
                r["remind_at"] = remind_dt.isoformat()
                due.append(r)
        else:
            # One-off: fire if past due and not yet notified (generous: up to 60 min late)
            if remind_dt <= until and remind_dt >= now - timedelta(minutes=60) and not r.get("notified_at"):
                due.append(r)

    return due


def mark_notified(db_path: str, reminder_id: int) -> None:
    """Record that a reminder has been shown to the user right now."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect(db_path)
    conn.execute(
        "UPDATE reminders SET notified_at = ? WHERE id = ?",
        (now, reminder_id),
    )
    conn.commit()
    conn.close()


def _recurrence_step(recurrence: str) -> timedelta:
    if recurrence == RECURRENCE_DAILY:
        return timedelta(days=1)
    if recurrence == RECURRENCE_WEEKLY:
        return timedelta(weeks=1)
    if recurrence == RECURRENCE_MONTHLY:
        return timedelta(days=30)
    return timedelta(weeks=1)
