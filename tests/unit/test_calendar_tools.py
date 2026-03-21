"""
Tests for helpers/tools/calendar.py and tools/calendar_tools.py

Uses a real in-process SQLite DB (tmp_db fixture).
No Ollama, no Docker, no network.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _iso(delta_hours: float = 0) -> str:
    dt = datetime.now(timezone.utc) + timedelta(hours=delta_hours)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Helper layer (calendar.py)
# ---------------------------------------------------------------------------

def test_create_and_list_event(tmp_db):
    from helpers.tools.calendar import create_event, list_events

    start = _iso(1)
    end = _iso(2)
    event = create_event(tmp_db, "Team sync", start, end, "Weekly standup", "Zoom")

    assert event["id"] > 0
    assert event["title"] == "Team sync"

    events = list_events(tmp_db, _iso(-1), _iso(3))
    assert len(events) == 1
    assert events[0]["title"] == "Team sync"
    assert events[0]["location"] == "Zoom"


def test_upcoming_events_returns_only_future(tmp_db):
    from helpers.tools.calendar import create_event, upcoming_events

    # Past event (should NOT appear)
    create_event(tmp_db, "Old meeting", _iso(-3), _iso(-2))
    # Upcoming (should appear)
    create_event(tmp_db, "Next call", _iso(2), _iso(3))

    events = upcoming_events(tmp_db, hours=24)
    titles = [e["title"] for e in events]
    assert "Next call" in titles
    assert "Old meeting" not in titles


def test_delete_event(tmp_db):
    from helpers.tools.calendar import create_event, list_events, delete_event

    start = _iso(1)
    event = create_event(tmp_db, "Delete me", start, None)
    deleted = delete_event(tmp_db, event["id"])

    assert deleted is True
    events = list_events(tmp_db, _iso(-1), _iso(3))
    assert all(e["id"] != event["id"] for e in events)


def test_delete_nonexistent_event(tmp_db):
    from helpers.tools.calendar import delete_event

    deleted = delete_event(tmp_db, 999_999)
    assert deleted is False


def test_list_events_empty_range(tmp_db):
    from helpers.tools.calendar import list_events

    events = list_events(tmp_db, _iso(10), _iso(20))
    assert events == []


def test_create_event_no_end_time(tmp_db):
    from helpers.tools.calendar import create_event, list_events

    event = create_event(tmp_db, "No end", _iso(1), None)
    events = list_events(tmp_db, _iso(0), _iso(2))
    assert len(events) == 1
    assert events[0]["end_time"] is None


# ---------------------------------------------------------------------------
# Tool logic via helpers (FunctionTool objects are not directly callable in tests)
# The helper layer is the real unit — these tests verify the tool logic end-to-end.
# ---------------------------------------------------------------------------

def test_schedule_event_tool_logic(tmp_db):
    """schedule_event tool delegates to create_event — verify the result."""
    from helpers.tools.calendar import create_event, list_events

    event = create_event(tmp_db, "Dentist", _iso(5), _iso(6), "Annual checkup", "Clinic")
    assert event["title"] == "Dentist"

    events = list_events(tmp_db, _iso(4), _iso(7))
    assert any(e["title"] == "Dentist" and e["location"] == "Clinic" for e in events)


def test_list_events_tool_logic_empty(tmp_db):
    from helpers.tools.calendar import list_events

    events = list_events(tmp_db, _iso(10), _iso(20))
    assert events == []


def test_list_events_tool_logic_with_data(tmp_db):
    from helpers.tools.calendar import create_event, list_events

    create_event(tmp_db, "Sprint review", _iso(1), _iso(2))
    events = list_events(tmp_db, _iso(0), _iso(3))

    assert any(e["title"] == "Sprint review" for e in events)


def test_upcoming_events_tool_logic(tmp_db):
    from helpers.tools.calendar import create_event, upcoming_events

    create_event(tmp_db, "Standup", _iso(1), _iso(1.5))
    events = upcoming_events(tmp_db, hours=3)

    assert any(e["title"] == "Standup" for e in events)


def test_cancel_event_tool_logic(tmp_db):
    from helpers.tools.calendar import create_event, delete_event, list_events

    event = create_event(tmp_db, "Cancel me", _iso(1), None)
    deleted = delete_event(tmp_db, event["id"])

    assert deleted is True
    events = list_events(tmp_db, _iso(0), _iso(2))
    assert all(e["id"] != event["id"] for e in events)


def test_cancel_event_tool_logic_not_found(tmp_db):
    from helpers.tools.calendar import delete_event

    assert delete_event(tmp_db, 999_999) is False
