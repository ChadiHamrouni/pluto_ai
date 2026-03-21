from __future__ import annotations

from typing import Dict, List


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


def build_system_prompt(base_instructions: str, memory_context: str = "") -> str:
    """
    Combine base agent instructions with an optional memory context block.

    The memory context is appended only when it is non-empty, separated
    by a clear visual divider so the model can distinguish it from the
    core instructions.
    """
    if not memory_context:
        return base_instructions.strip()

    return base_instructions.strip() + "\n\n---\n\n" + memory_context.strip()
