from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Command registry — single source of truth for all slash commands.
#
# Each entry: primary command → {"desc": str, "intent": str, "aliases": [...]}
#
# All commands route to the single Pluto agent. The slash prefix is stripped
# and replaced with a [intent] hint so the agent knows which tool domain to use.
#
# To add a new slash command:
#   1. Add an entry here.
#   2. Add a row to the hint table in instructions/agents/single_agent.md.
#   3. That's it — the frontend reads GET /chat/commands automatically.
# ---------------------------------------------------------------------------

COMMAND_REGISTRY: list[dict] = [
    {
        "cmd": "/note",
        "desc": "Create or manage notes",
        "intent": "note",
        "aliases": ["/notes"],
    },
    {
        "cmd": "/slides",
        "desc": "Generate a slide presentation",
        "intent": "slides",
        "aliases": ["/slide"],
    },
    {
        "cmd": "/research",
        "desc": "Deep research with multiple sources",
        "intent": "research",
        "aliases": [],
    },
    {
        "cmd": "/calendar",
        "desc": "Schedule or view calendar events",
        "intent": "calendar",
        "aliases": ["/schedule", "/event"],
    },
    {
        "cmd": "/remember",
        "desc": "Save something to memory",
        "intent": "memory",
        "aliases": ["/memory"],
    },
    {
        "cmd": "/forget",
        "desc": "Delete a memory",
        "intent": "forget",
        "aliases": [],
    },
    {
        "cmd": "/task",
        "desc": "Manage tasks and kanban board",
        "intent": "task",
        "aliases": ["/tasks"],
    },
    {
        "cmd": "/budget",
        "desc": "Track income, expenses, and savings goals",
        "intent": "budget",
        "aliases": [],
    },
    {
        "cmd": "/diagram",
        "desc": "Generate a Mermaid diagram as PNG",
        "intent": "diagram",
        "aliases": [],
    },
    {
        "cmd": "/dashboard",
        "desc": "Sync Obsidian vault and generate views",
        "intent": "dashboard",
        "aliases": ["/obsidian", "/vault"],
    },
]

# Flat alias → intent lookup built from the registry above
_ALIAS_TO_INTENT: dict[str, str] = {}
for _entry in COMMAND_REGISTRY:
    _ALIAS_TO_INTENT[_entry["cmd"]] = _entry["intent"]
    for _alias in _entry["aliases"]:
        _ALIAS_TO_INTENT[_alias] = _entry["intent"]


@dataclass
class ParsedCommand:
    intent: Optional[
        str
    ]  # "note" | "slides" | "memory" | "forget" | "research" | "calendar" | None
    content: str  # message with the slash command token stripped


def parse_command(message: str) -> ParsedCommand:
    """
    Detect an optional leading slash command in *message*.

    Returns ParsedCommand with:
    - intent = canonical routing target if a known command was found, else None
    - content = remainder of the message after stripping the command token

    Unknown slash commands are passed through unchanged (intent=None) so the
    orchestrator can handle them with its normal LLM routing.
    """
    stripped = message.strip()
    if not stripped.startswith("/"):
        return ParsedCommand(intent=None, content=message)

    parts = stripped.split(None, 1)
    token = parts[0].lower()
    content = parts[1] if len(parts) > 1 else ""

    intent = _ALIAS_TO_INTENT.get(token)
    if intent is None:
        return ParsedCommand(intent=None, content=message)

    return ParsedCommand(intent=intent, content=content)
