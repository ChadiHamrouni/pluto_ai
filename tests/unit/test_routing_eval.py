"""
Routing eval: deterministic slash-command routing accuracy.

Tests parse_command() and the _COMMAND_AGENTS dispatch table —
no LLM, no DB, no network.

These cover the deterministic half of the hybrid routing system.
LLM routing (Orchestrator handoffs) is tested separately via mocked SDK calls.
"""
from __future__ import annotations

import pytest

from helpers.agents.routing.command_parser import parse_command


# ---------------------------------------------------------------------------
# Slash command parsing — ground-truth routing table
# ---------------------------------------------------------------------------

SLASH_ROUTING_CASES = [
    # (input_message, expected_intent)
    # Notes
    ("/note Save this idea", "note"),
    ("/notes List my notes", "note"),
    ("/note", "note"),
    # Slides
    ("/slides Make a deck about AI", "slides"),
    ("/slide Present quantum computing", "slides"),
    # Memory
    ("/remember I like coffee", "memory"),
    ("/memory What do I know?", "memory"),
    # Forget
    ("/forget I don't like coffee anymore", "forget"),
    # Calendar
    ("/calendar Show this week", "calendar"),
    ("/schedule Meeting tomorrow 3pm", "calendar"),
    ("/event Add dentist Friday", "calendar"),
    # Tasks
    ("/task Add a new task", "task"),
    ("/tasks Show all tasks", "task"),
    # Budget
    ("/budget Show summary", "budget"),
    # Diagram
    ("/diagram Draw a flowchart", "diagram"),
    # Dashboard / Obsidian
    ("/dashboard Sync vault", "dashboard"),
    ("/obsidian Sync vault", "dashboard"),
    ("/vault Sync vault", "dashboard"),
    # Unknown slash — should fall through (intent=None)
    ("/unknown do something", None),
    ("/foo bar", None),
]


@pytest.mark.parametrize("message,expected_intent", SLASH_ROUTING_CASES)
def test_slash_command_routing(message: str, expected_intent):
    parsed = parse_command(message)
    assert parsed.intent == expected_intent, (
        f"parse_command({message!r}) → intent={parsed.intent!r}, expected={expected_intent!r}"
    )


# ---------------------------------------------------------------------------
# Content stripping
# ---------------------------------------------------------------------------

def test_parse_command_strips_command_token():
    parsed = parse_command("/note Save this idea about AI")
    assert parsed.content == "Save this idea about AI"


def test_parse_command_empty_content():
    parsed = parse_command("/note")
    assert parsed.content == ""


def test_parse_command_no_slash_passthrough():
    parsed = parse_command("What is the weather?")
    assert parsed.intent is None
    assert parsed.content == "What is the weather?"


def test_parse_command_case_insensitive():
    parsed = parse_command("/NOTE Save upper case")
    assert parsed.intent == "note"


def test_parse_command_preserves_multi_word_content():
    parsed = parse_command("/note Find out about gravitational wave detection methods")
    assert parsed.intent == "note"
    assert parsed.content == "Find out about gravitational wave detection methods"


def test_parse_command_calendar_aliases():
    for cmd in ["/calendar", "/schedule", "/event"]:
        parsed = parse_command(f"{cmd} book a call")
        assert parsed.intent == "calendar", f"{cmd} should route to calendar"


# ---------------------------------------------------------------------------
# _COMMAND_AGENTS dispatch table completeness
# ---------------------------------------------------------------------------

def test_command_agents_covers_all_known_intents():
    """Every intent that parse_command can return is handled by the single Pluto agent.

    With the single-agent architecture, all slash commands are forwarded to Pluto
    with a [intent] hint prefix. This test verifies that every registered intent
    is a known, expected intent — i.e. the COMMAND_REGISTRY is complete.
    """
    import sys
    from unittest.mock import MagicMock

    # Stub out missing optional dependencies so the import chain resolves
    for mod_name in ("ddgs", "colpali_engine", "torch", "PIL", "pdf2image"):
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

    from helpers.agents.routing.command_parser import _ALIAS_TO_INTENT

    # All intents that parse_command can return (excluding pass-through Nones)
    all_intents = {v for v in _ALIAS_TO_INTENT.values() if v is not None}

    # All known intents in the single-agent hint system (memory/forget handled inline)
    known_intents = {
        "note", "slides", "calendar",
        "task", "budget", "diagram", "dashboard",
        "memory", "forget", "reminders",
    }

    unknown = all_intents - known_intents
    assert not unknown, f"Unexpected intents not in known set: {unknown}"
