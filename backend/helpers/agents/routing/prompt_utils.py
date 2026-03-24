from __future__ import annotations

from datetime import datetime
from typing import Dict, List
from zoneinfo import ZoneInfo

from helpers.core.config_loader import load_config


def format_memory_context(memories: list) -> str:
    """
    Format all memory facts into a compact block for the system prompt.

    Grouped by category so the model can scan them easily.
    """
    if not memories:
        return ""

    by_category: dict[str, list[str]] = {}
    for mem in memories:
        category = (
            mem.get("category", "general")
            if isinstance(mem, dict)
            else getattr(mem, "category", "general")
        )
        content = mem.get("content", "") if isinstance(mem, dict) else getattr(mem, "content", "")
        by_category.setdefault(category, []).append(content)

    lines: List[str] = ["## What I know about you\n"]
    for category, facts in by_category.items():
        lines.append(f"**{category.capitalize()}**")
        for fact in facts:
            lines.append(f"- {fact}")
        lines.append("")

    return "\n".join(lines)


def format_chat_history(history: list) -> List[Dict[str, str]]:
    """
    Convert a list of ChatMessage objects (or dicts) to the OpenAI
    message format: [{"role": "...", "content": "..."}, ...].

    Filters out any entries missing a role or content to avoid API errors.
    """
    messages: List[Dict[str, str]] = []
    for msg in history:
        if isinstance(msg, dict):
            role = msg.get("role", "")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "role", "")
            content = getattr(msg, "content", "")

        if role and content:
            messages.append({"role": role, "content": content})

    return messages


def _build_context_block() -> str:
    """Return a small context block with the current date/time and user location."""
    cfg = load_config().get("user", {})
    tz_name = cfg.get("timezone", "UTC")
    location = cfg.get("location", "")
    try:
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:
        now = datetime.utcnow()
    date_str = now.strftime("%A, %d %B %Y")
    time_str = now.strftime("%H:%M")
    parts = [f"## Context\n- Date: {date_str}\n- Time: {time_str} ({tz_name})"]
    if location:
        parts.append(f"- Location: {location}")
    return "\n".join(parts)


def build_system_prompt(base_instructions: str, memory_context: str = "") -> str:
    """
    Combine base agent instructions with an optional memory context block.

    The memory context is appended only when it is non-empty, separated
    by a clear visual divider so the model can distinguish it from the
    core instructions.
    """
    context_block = _build_context_block()
    parts = [base_instructions.strip(), "---", context_block]
    if memory_context:
        parts += ["---", memory_context.strip()]
    return "\n\n".join(parts)
