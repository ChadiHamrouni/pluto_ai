"""Reminder @function_tool wrappers."""

from __future__ import annotations

import json

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.reminders import (
    create_reminder as _create_reminder,
    delete_reminder as _delete_reminder,
    get_db_path,
    list_reminders as _list_reminders,
)

logger = get_logger(__name__)


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
        remind_at: ISO-8601 datetime in UTC when to fire the reminder
                   (e.g. "2025-06-15T17:00:00Z"). Always resolve relative
                   expressions ("Friday at 6pm", "tomorrow morning") to an
                   absolute UTC datetime before calling.
        recurrence: How often to repeat — '' (once, default), 'daily', 'weekly',
                    or 'monthly'. Use 'monthly' for "every 1st of the month" etc.

    Returns:
        Confirmation string with reminder id and scheduled time.
    """
    db_path = get_db_path()
    rec = recurrence.strip().lower() if recurrence else ""
    try:
        reminder = _create_reminder(db_path, title, remind_at, rec)
        rec_str = f" (recurs {rec})" if rec else ""
        return f'Reminder set (id={reminder["id"]}): "{title}" at {remind_at}{rec_str}'
    except Exception as exc:
        logger.error("set_reminder failed: %s", exc)
        return f"Failed to set reminder: {exc}"


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
