"""Reminder @function_tool wrappers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.reminders import (
    create_reminder as _create_reminder,
    create_reminders_batch as _create_reminders_batch,
    delete_reminder as _delete_reminder,
    get_db_path,
    list_reminders as _list_reminders,
)
from helpers.tools.idempotency import make_key as _make_key
from models.batch import ReminderSpec

logger = get_logger(__name__)

_LOCAL_OFFSET = timedelta(hours=1)


def _local_to_utc(iso: str) -> str:
    """Treat iso as local time (UTC+1, no offset) and return a UTC ISO string."""
    clean = iso.rstrip("Z")
    if "+" in clean[10:]:
        clean = clean[:clean.index("+", 10)]
    dt = datetime.fromisoformat(clean)
    return (dt - _LOCAL_OFFSET).strftime("%Y-%m-%dT%H:%M:%SZ")


@function_tool
def set_reminder(
    title: str,
    remind_at: str,
    recurrence: str = "",
) -> str:
    """
    Set a reminder that will trigger a desktop notification at the specified time.

    Args:
        title: What to remind the user about (e.g. "Get a haircut", "Pay electricity bill").
        remind_at: Local time as ISO-8601 WITHOUT timezone offset (e.g. "2025-06-15T10:25:00").
                   Always use the time the user stated directly — do NOT convert to UTC.
                   Resolve relative expressions ("Friday at 6pm", "tomorrow at 9am") to an
                   absolute local datetime string first.
        recurrence: How often to repeat — '' (once, default), 'daily', 'weekly',
                    or 'monthly'. Use 'monthly' for "every 1st of the month" etc.

    Returns:
        Confirmation string with reminder id and scheduled time.
    """
    db_path = get_db_path()
    rec = recurrence.strip().lower() if recurrence else ""
    try:
        utc_time = _local_to_utc(remind_at)
        reminder = _create_reminder(db_path, title, utc_time, rec)
        rec_str = f" (recurs {rec})" if rec else ""
        return f'Reminder set (id={reminder["id"]}): "{title}" at {remind_at}{rec_str}'
    except Exception as exc:
        logger.error("set_reminder failed: %s", exc)
        return f"Failed to set reminder: {exc}"


@function_tool
def create_reminders(reminders: list[ReminderSpec]) -> str:
    """
    Create one or more reminders. Use for any request to set reminders —
    single or multiple. Pass a list with one item for a single reminder.

    Each item is a ReminderSpec with:
        title      (required) — what to remind the user about
        remind_at  (required) — local ISO-8601 without offset, e.g. "2026-04-21T09:00:00"
        recurrence (optional) — '' | 'daily' | 'weekly' | 'monthly'

    Idempotency: re-submitting the same (title, remind_at) pair is safe — duplicates
    are skipped and reported as status='skipped'.

    Returns:
        Summary string: how many created / skipped.
    """
    db_path = get_db_path()
    prepped: list[dict] = []
    for r in reminders:
        title = r.title
        remind_at = r.remind_at
        if not title or not remind_at:
            continue
        try:
            utc_time = _local_to_utc(remind_at)
        except Exception as exc:
            logger.error("create_reminders: bad time for '%s': %s", title, exc)
            continue
        prepped.append({
            "title": title,
            "remind_at": utc_time,
            "recurrence": r.recurrence.strip().lower(),
            "idempotency_key": _make_key(title, remind_at),
        })

    if not prepped:
        return "No valid reminders to create."

    try:
        results = _create_reminders_batch(db_path, prepped)
    except Exception as exc:
        logger.error("create_reminders failed: %s", exc)
        return f"Failed to create reminders: {exc}"

    created = [r for r in results if r["status"] == "created"]
    skipped = [r for r in results if r["status"] == "skipped"]
    lines = [f"Created {len(created)} reminder(s), skipped {len(skipped)} duplicate(s)."]
    for r in created:
        lines.append(f"  ✓ [{r['id']}] {r['title']} at {r['remind_at']}")
    for r in skipped:
        lines.append(f"  ~ [{r['id']}] skipped (duplicate)")
    return "\n".join(lines)


@function_tool
def list_reminders() -> str:
    """
    List all active reminders.

    Returns:
        JSON array of reminders, or a plain-text message if none exist.
    """
    db_path = get_db_path()
    try:
        reminders = _list_reminders(db_path)
        if not reminders:
            return "No reminders set."
        return json.dumps(reminders, indent=2)
    except Exception as exc:
        logger.error("list_reminders failed: %s", exc)
        return f"Failed to list reminders: {exc}"


@function_tool
def delete_reminder(reminder_id: int) -> str:
    """
    Delete a reminder by its id.

    Args:
        reminder_id: The numeric id returned when the reminder was created.

    Returns:
        Confirmation or error string.
    """
    db_path = get_db_path()
    try:
        deleted = _delete_reminder(db_path, reminder_id)
        if deleted:
            return f"Reminder {reminder_id} deleted."
        return f"No reminder found with id={reminder_id}."
    except Exception as exc:
        logger.error("delete_reminder failed: %s", exc)
        return f"Failed to delete reminder: {exc}"
