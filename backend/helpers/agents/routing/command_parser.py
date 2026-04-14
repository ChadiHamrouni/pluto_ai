from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Command registry — single source of truth for all slash commands.
#
# Each entry maps a primary slash command to:
#   - desc:       user-visible description (shown in the frontend command menu)
#   - intent:     short routing tag injected as "[intent]" before the message
#   - tool_group: name of the tool subset the agent gets for this intent
#                 (see agent/single.py TOOL_GROUPS). "core" = fallback set.
#   - aliases:    alternative tokens that map to the same intent
#
# To add a new slash command:
#   1. Add an entry here with the correct tool_group.
#   2. Add that group to TOOL_GROUPS in agent/single.py.
#   3. Add a domain instructions file at instructions/agents/domain/<intent>.md.
#   4. Add a row to the hint table in instructions/agents/single_agent.md.
#   5. The frontend reads GET /chat/commands automatically — nothing else needed.
# ---------------------------------------------------------------------------

COMMAND_REGISTRY: list[dict] = [
    {
        "cmd": "/note",
        "desc": "Create or manage notes",
        "intent": "note",
        "tool_group": "notes",
        "aliases": ["/notes"],
    },
    {
        "cmd": "/slides",
        "desc": "Generate a slide presentation",
        "intent": "slides",
        "tool_group": "slides",
        "aliases": ["/slide"],
    },
    {
        "cmd": "/calendar",
        "desc": "Schedule or view calendar events",
        "intent": "calendar",
        "tool_group": "calendar",
        "aliases": ["/schedule", "/event"],
    },
    {
        "cmd": "/remember",
        "desc": "Save something to memory",
        "intent": "memory",
        "tool_group": "memory",
        "aliases": ["/memory"],
    },
    {
        "cmd": "/forget",
        "desc": "Delete a memory",
        "intent": "forget",
        "tool_group": "memory",
        "aliases": [],
    },
    {
        "cmd": "/task",
        "desc": "Manage tasks and kanban board",
        "intent": "task",
        "tool_group": "tasks",
        "aliases": ["/tasks"],
    },
    {
        "cmd": "/budget",
        "desc": "Track income, expenses, and savings goals",
        "intent": "budget",
        "tool_group": "budget",
        "aliases": [],
    },
    {
        "cmd": "/diagram",
        "desc": "Generate a Mermaid diagram as PNG",
        "intent": "diagram",
        "tool_group": "diagrams",
        "aliases": [],
    },
    {
        "cmd": "/dashboard",
        "desc": "Sync Obsidian vault and generate views",
        "intent": "dashboard",
        "tool_group": "vault",
        "aliases": ["/obsidian", "/vault"],
    },
    {
        "cmd": "/remind",
        "desc": "Set a reminder notification",
        "intent": "reminders",
        "tool_group": "reminders",
        "aliases": ["/reminder", "/reminders"],
    },
]

# Flat alias → intent lookup built from the registry above
_ALIAS_TO_INTENT: dict[str, str] = {}
# Flat intent → tool_group lookup built from the registry above
_INTENT_TO_TOOL_GROUP: dict[str, str] = {}

for _entry in COMMAND_REGISTRY:
    _ALIAS_TO_INTENT[_entry["cmd"]] = _entry["intent"]
    _INTENT_TO_TOOL_GROUP[_entry["intent"]] = _entry["tool_group"]
    for _alias in _entry["aliases"]:
        _ALIAS_TO_INTENT[_alias] = _entry["intent"]


@dataclass
class ParsedCommand:
    intent: Optional[str]      # "note" | "slides" | "memory" | … | None
    tool_group: Optional[str]  # "notes" | "slides" | "memory" | … | None
    content: str               # message with the slash command token stripped


def parse_command(message: str) -> ParsedCommand:
    """
    Detect an optional leading slash command in *message*.

    Returns ParsedCommand with:
    - intent     = canonical routing tag if a known command was found, else None
    - tool_group = which subset of tools to expose for this intent, else None
    - content    = remainder of the message after stripping the command token

    Unknown slash commands are passed through unchanged (intent=None) so the
    orchestrator handles them with normal LLM routing and the full tool set.
    """
    stripped = message.strip()
    if not stripped.startswith("/"):
        return ParsedCommand(intent=None, tool_group=None, content=message)

    parts = stripped.split(None, 1)
    token = parts[0].lower()
    content = parts[1] if len(parts) > 1 else ""

    intent = _ALIAS_TO_INTENT.get(token)
    if intent is None:
        return ParsedCommand(intent=None, tool_group=None, content=message)

    tool_group = _INTENT_TO_TOOL_GROUP.get(intent)
    return ParsedCommand(intent=intent, tool_group=tool_group, content=content)
