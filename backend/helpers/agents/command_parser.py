from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Maps slash command aliases to a canonical intent
_COMMANDS: dict[str, str] = {
    "/note": "note",
    "/notes": "note",
    "/slides": "slides",
    "/slide": "slides",
    "/remember": "memory",
    "/memory": "memory",
    "/forget": "forget",
    "/research": "research",
    "/calendar": "calendar",
    "/schedule": "calendar",
    "/event": "calendar",
}


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

    intent = _COMMANDS.get(token)
    if intent is None:
        return ParsedCommand(intent=None, content=message)

    return ParsedCommand(intent=intent, content=content)
