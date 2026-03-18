from __future__ import annotations

from typing import Any, Dict, List


def format_memory_context(memories: list) -> str:
    """
    Format a list of memory entries (dicts or MemoryEntry-like objects)
    into a readable block suitable for inclusion in a system prompt.

    Each entry is rendered as a numbered item showing its category,
    tags, and content.
    """
    if not memories:
        return ""

    lines: List[str] = ["## Relevant Memory Context\n"]
    for i, mem in enumerate(memories, start=1):
        # Support both dict and object access
        if isinstance(mem, dict):
            category = mem.get("category", "unknown")
            tags = mem.get("tags", [])
            content = mem.get("content", "")
            score = mem.get("relevance_score")
        else:
            category = getattr(mem, "category", "unknown")
            tags = getattr(mem, "tags", [])
            content = getattr(mem, "content", "")
            score = getattr(mem, "relevance_score", None)

        tag_str = ", ".join(tags) if tags else "none"
        score_str = f" (score: {score:.3f})" if score is not None else ""
        lines.append(
            f"{i}. [{category.upper()}]{score_str} — tags: {tag_str}\n   {content}"
        )

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

    return (
        base_instructions.strip()
        + "\n\n---\n\n"
        + memory_context.strip()
    )
