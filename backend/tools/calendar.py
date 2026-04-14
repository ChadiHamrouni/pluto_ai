"""Calendar @function_tool wrappers for the CalendarAgent."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

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
from helpers.tools.calendar import (
    update_event as _update_event,
)

logger = get_logger(__name__)

# User's local offset — stored as UTC, displayed as UTC+1 (Tunis/CET)
_LOCAL_OFFSET = timedelta(hours=1)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _local_to_utc(iso: str) -> str:
    """Treat iso as local time (UTC+1, no offset) and return a UTC ISO string."""
    # Strip any Z or offset suffix — we always treat input as local
    clean = iso.rstrip("Z")
    if "+" in clean[10:]:  # offset present after the date part
        clean = clean[:clean.index("+", 10)]
    dt = datetime.fromisoformat(clean)  # naive, interpreted as local
    utc_dt = dt - _LOCAL_OFFSET
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_to_local_str(iso: str | None) -> str | None:
    """Convert a stored UTC ISO string to local display string (UTC+1)."""
    if not iso:
        return iso
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (dt + _LOCAL_OFFSET).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return iso


def _localise_event(event: dict) -> dict:
    """Return a copy of the event dict with times converted to local timezone for display."""
    return {
        **event,
        "start_time": _utc_to_local_str(event.get("start_time")),
        "end_time": _utc_to_local_str(event.get("end_time")),
    }


@function_tool
def schedule_event(
    title: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
    location: str = "",
    recurrence: str = "",
) -> str:
    """
    Create a calendar event.

    Args:
        title: Short event title (e.g. "Team meeting").
        start_time: Local time as ISO-8601 WITHOUT timezone offset (e.g. "2025-06-15T15:30:00").
                    Always use the time the user stated directly — do not convert to UTC.
                    If the user gives a relative expression like "tomorrow at 3pm",
                    resolve it to an absolute local datetime string first.
        end_time: Local ISO-8601 end time without offset (optional). Leave empty if not specified.
        description: Optional notes about the event.
        location: Optional place or URL.
        recurrence: Recurrence pattern — '' (one-off, default), 'daily', or 'weekly'.
                    For 'weekly', start_time sets the anchor day-of-week and time.
                    Use 'weekly' whenever the user says "every Monday", "every week", etc.

    Returns:
        Confirmation string with the event id and scheduled time.
    """
    db_path = get_db_path()
    rec = recurrence.strip().lower() if recurrence else ""
    try:
        utc_start = _local_to_utc(start_time)
        utc_end = _local_to_utc(end_time) if end_time else None
        event = _create_event(db_path, title, utc_start, utc_end, description, location, rec)
        end_str = f" → {end_time}" if end_time else ""
        rec_str = f" (recurs {rec})" if rec else ""
        return f'Event created (id={event["id"]}): "{title}" on {start_time}{end_str}{rec_str}'
    except Exception as exc:
        logger.error("schedule_event failed: %s", exc)
        return f"Failed to create event: {exc}"


@function_tool
def list_events(from_time: str = "", to_time: str = "") -> str:
    """
    List calendar events within a time range.

    Args:
        from_time: Local ISO-8601 start of range without offset (defaults to now if empty).
        to_time:   Local ISO-8601 end of range without offset (defaults to 7 days from now if empty).

    Returns:
        JSON array of events with times in local time, or a plain-text message if none found.
    """
    db_path = get_db_path()
    now = datetime.now(timezone.utc)

    utc_from = _local_to_utc(from_time) if from_time else now.strftime("%Y-%m-%dT%H:%M:%SZ")
    utc_to = _local_to_utc(to_time) if to_time else (now + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        events = _list_events(db_path, utc_from, utc_to)
        if not events:
            return f"No events found between {from_time} and {to_time}."
        return json.dumps([_localise_event(e) for e in events], indent=2)
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
        return json.dumps([_localise_event(e) for e in events], indent=2)
    except Exception as exc:
        logger.error("upcoming_events failed: %s", exc)
        return f"Failed to fetch upcoming events: {exc}"


@function_tool
def update_event(
    event_id: int,
    title: str = "",
    start_time: str = "",
    end_time: str = "",
    description: str = "",
    location: str = "",
    recurrence: str = "",
) -> str:
    """
    Update an existing calendar event. Only pass fields you want to change.

    Args:
        event_id: The numeric id of the event to update.
        title: New title (leave empty to keep existing).
        start_time: New local start time without offset (leave empty to keep existing).
        end_time: New local end time without offset (leave empty to keep existing).
        description: New description (leave empty to keep existing).
        location: New location (leave empty to keep existing).
        recurrence: New recurrence pattern — '', 'daily', or 'weekly' (leave empty to keep existing).

    Returns:
        Confirmation string or error.
    """
    db_path = get_db_path()
    try:
        updated = _update_event(
            db_path,
            event_id,
            title=title or None,
            start_time=_local_to_utc(start_time) if start_time else None,
            end_time=_local_to_utc(end_time) if end_time else None,
            description=description or None,
            location=location or None,
            recurrence=recurrence.strip().lower() if recurrence else None,
        )
        if updated is None:
            return f"No event found with id={event_id}."
        local = _localise_event(updated)
        return f'Event {event_id} updated: "{local["title"]}" {local["start_time"]} → {local["end_time"]}'
    except Exception as exc:
        logger.error("update_event failed: %s", exc)
        return f"Failed to update event: {exc}"


@function_tool
def cancel_event(event_id: int) -> str:
    """
    Delete a calendar event by its id.

    IMPORTANT: Never guess the event id. Always call list_events first to find
    the correct event by matching BOTH title AND start_time, then pass that id here.
    Multiple events can share the same title — the start_time is what distinguishes them.

    Args:
        event_id: The numeric id from list_events for the specific occurrence to delete.

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
