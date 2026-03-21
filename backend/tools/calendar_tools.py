"""Calendar @function_tool wrappers for the CalendarAgent."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.calendar import (
    create_event as _create_event,
)
from helpers.tools.calendar import (
    delete_event as _delete_event,
)
from helpers.tools.calendar import (
    get_db_path,
)
from helpers.tools.calendar import (
    list_events as _list_events,
)
from helpers.tools.calendar import (
    upcoming_events as _upcoming_events,
)

logger = get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@function_tool
def schedule_event(
    title: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """
    Create a calendar event.

    Args:
        title: Short event title (e.g. "Team meeting").
        start_time: ISO-8601 datetime in UTC (e.g. "2025-06-15T14:00:00Z").
                    If the user gives a relative expression like "tomorrow at 3pm",
                    resolve it to an absolute ISO-8601 string first.
        end_time: ISO-8601 end time (optional). Leave empty if not specified.
        description: Optional notes about the event.
        location: Optional place or URL.

    Returns:
        Confirmation string with the event id and scheduled time.
    """
    db_path = get_db_path()
    end = end_time if end_time else None
    try:
        event = _create_event(db_path, title, start_time, end, description, location)
        end_str = f" → {end_time}" if end_time else ""
        return f'Event created (id={event["id"]}): "{title}" on {start_time}{end_str}'
    except Exception as exc:
        logger.error("schedule_event failed: %s", exc)
        return f"Failed to create event: {exc}"


@function_tool
def list_events(from_time: str = "", to_time: str = "") -> str:
    """
    List calendar events within a time range.

    Args:
        from_time: ISO-8601 start of range (defaults to now if empty).
        to_time:   ISO-8601 end of range (defaults to 7 days from now if empty).

    Returns:
        JSON array of events, or a plain-text message if none found.
    """
    from datetime import timedelta

    db_path = get_db_path()
    now = datetime.now(timezone.utc)

    if not from_time:
        from_time = now.isoformat()
    if not to_time:
        to_time = (now + timedelta(days=7)).isoformat()

    try:
        events = _list_events(db_path, from_time, to_time)
        if not events:
            return f"No events found between {from_time} and {to_time}."
        return json.dumps(events, indent=2)
    except Exception as exc:
        logger.error("list_events failed: %s", exc)
        return f"Failed to list events: {exc}"


@function_tool
def upcoming_events(hours: int = 24) -> str:
    """
    Return events starting within the next N hours.

    Args:
        hours: Look-ahead window in hours (default 24).

    Returns:
        JSON array of upcoming events, or a plain-text message if none.
    """
    db_path = get_db_path()
    try:
        events = _upcoming_events(db_path, hours)
        if not events:
            return f"No events in the next {hours} hours."
        return json.dumps(events, indent=2)
    except Exception as exc:
        logger.error("upcoming_events failed: %s", exc)
        return f"Failed to fetch upcoming events: {exc}"


@function_tool
def cancel_event(event_id: int) -> str:
    """
    Delete a calendar event by its id.

    Args:
        event_id: The numeric id returned when the event was created.

    Returns:
        Confirmation or error string.
    """
    db_path = get_db_path()
    try:
        deleted = _delete_event(db_path, event_id)
        if deleted:
            return f"Event {event_id} cancelled."
        return f"No event found with id={event_id}."
    except Exception as exc:
        logger.error("cancel_event failed: %s", exc)
        return f"Failed to cancel event: {exc}"
