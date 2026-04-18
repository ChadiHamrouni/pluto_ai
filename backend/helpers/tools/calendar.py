"""Helper functions for calendar/event persistence."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.obsidian import sync_vault_background

logger = get_logger(__name__)

# Supported recurrence values
RECURRENCE_WEEKLY = "weekly"
RECURRENCE_DAILY = "daily"


def get_db_path() -> str:
    return load_config()["memory"]["db_path"]


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


def update_event(
    db_path: str,
    event_id: int,
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    description: str | None = None,
    location: str | None = None,
    recurrence: str | None = None,
) -> dict | None:
    """Update one or more fields of an existing event. Returns updated row or None if not found."""
    fields, values = [], []
    if title is not None:
        fields.append("title = ?"); values.append(title)
    if start_time is not None:
        fields.append("start_time = ?"); values.append(start_time)
    if end_time is not None:
        fields.append("end_time = ?"); values.append(end_time)
    if description is not None:
        fields.append("description = ?"); values.append(description)
    if location is not None:
        fields.append("location = ?"); values.append(location)
    if recurrence is not None:
        fields.append("recurrence = ?"); values.append(recurrence)
    if not fields:
        return None
    values.append(event_id)
    conn = _connect(db_path)
    cursor = conn.execute(f"UPDATE events SET {', '.join(fields)} WHERE id = ?", values)
    conn.commit()
    if cursor.rowcount == 0:
        conn.close()
        return None
    row = conn.execute(
        "SELECT id, title, start_time, end_time, description, location, recurrence FROM events WHERE id = ?",
        (event_id,),
    ).fetchone()
    conn.close()
    logger.info("Updated event %d", event_id)
    sync_vault_background()
    return _row_to_dict(row) if row else None


def create_event(
    db_path: str,
    title: str,
    start_time: str,
    end_time: str | None,
    description: str = "",
    location: str = "",
    recurrence: str = "",
) -> dict:
    """Insert an event. start_time / end_time must be ISO-8601 strings (UTC).

    recurrence: '' (one-off), 'daily', or 'weekly'.
    For weekly events, start_time determines the day-of-week anchor.
    """
    conn = _connect(db_path)
    cursor = conn.execute(
        """INSERT INTO events (title, start_time, end_time, description, location, recurrence)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (title, start_time, end_time, description, location, recurrence),
    )
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    logger.info("Created event %d: %s at %s (recurrence=%r)", event_id, title, start_time, recurrence)
    result = {
        "id": event_id,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "recurrence": recurrence,
    }
    sync_vault_background()
    return result


def _parse_naive_utc(iso: str) -> datetime:
    """Parse any ISO-8601 string to a naive UTC datetime for comparison."""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None) - dt.utcoffset()
    return dt


def _expand_recurring(row: dict, from_dt: datetime, to_dt: datetime) -> list[dict]:
    """Expand a recurring event row into occurrences within [from_dt, to_dt].
    from_dt and to_dt must be naive UTC datetimes.
    """
    recurrence = row.get("recurrence", "")
    if not recurrence:
        return []

    try:
        anchor = _parse_naive_utc(row["start_time"])
    except ValueError:
        return []

    duration: timedelta | None = None
    if row.get("end_time"):
        try:
            end_anchor = _parse_naive_utc(row["end_time"])
            duration = end_anchor - anchor
        except ValueError:
            pass

    if recurrence == RECURRENCE_DAILY:
        step = timedelta(days=1)
    elif recurrence == RECURRENCE_WEEKLY:
        step = timedelta(weeks=1)
    else:
        return []

    # Jump anchor forward to first occurrence >= from_dt
    current = anchor
    if current < from_dt:
        diff = from_dt - current
        steps = int(diff / step)
        current = current + step * steps
        if current < from_dt:
            current += step

    occurrences: list[dict] = []
    while current <= to_dt:
        occ_end = (current + duration).isoformat() if duration is not None else row.get("end_time")
        occurrences.append({
            **row,
            "start_time": current.isoformat() + "Z",
            "end_time": occ_end,
            "recurring_instance": True,
        })
        current += step

    return occurrences


def list_events(db_path: str, from_time: str, to_time: str) -> list[dict]:
    """Return events (and expanded recurrences) whose start_time falls within [from_time, to_time]."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT id, title, start_time, end_time, description, location, recurrence
           FROM events
           ORDER BY start_time ASC""",
    ).fetchall()
    conn.close()

    from_dt = _parse_naive_utc(from_time)
    to_dt = _parse_naive_utc(to_time)

    results: list[dict] = []
    for row in rows:
        d = _row_to_dict(row)
        recurrence = d.get("recurrence", "")
        if recurrence:
            results.extend(_expand_recurring(d, from_dt, to_dt))
        else:
            try:
                start = _parse_naive_utc(d["start_time"])
                if from_dt <= start <= to_dt:
                    results.append(d)
            except ValueError:
                pass

    results.sort(key=lambda e: e["start_time"])
    return results


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


def create_events_batch(
    db_path: str,
    events: list[dict],
) -> list[dict]:
    """Insert multiple events atomically. Each dict must have 'title' and 'start_time' (UTC ISO-8601).
    Optional keys: end_time, description, location, recurrence, idempotency_key.
    Returns list of result dicts with status='created'|'skipped' and the event data.
    """
    results: list[dict] = []
    conn = _connect(db_path)
    try:
        for item in events:
            idem_key = item.get("idempotency_key", "")
            if idem_key:
                existing = conn.execute(
                    "SELECT id, title, start_time FROM events WHERE idempotency_key = ?",
                    (idem_key,),
                ).fetchone()
                if existing:
                    results.append({"status": "skipped", "id": existing["id"], "idempotency_key": idem_key})
                    continue

            cursor = conn.execute(
                """INSERT INTO events (title, start_time, end_time, description, location, recurrence, idempotency_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["title"],
                    item["start_time"],
                    item.get("end_time"),
                    item.get("description", ""),
                    item.get("location", ""),
                    item.get("recurrence", ""),
                    idem_key,
                ),
            )
            results.append({
                "status": "created",
                "id": cursor.lastrowid,
                "title": item["title"],
                "start_time": item["start_time"],
                "idempotency_key": idem_key,
            })
            logger.info("Batch created event %d: %s", cursor.lastrowid, item["title"])
        conn.commit()
    finally:
        conn.close()
    sync_vault_background()
    return results
