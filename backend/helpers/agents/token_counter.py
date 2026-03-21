"""Lightweight token estimation for context window management.

Uses a simple character-based heuristic (~4 chars/token for English).
Accurate enough to trigger compaction thresholds without requiring a tokenizer.
"""

from __future__ import annotations

from helpers.core.config_loader import load_config


def _get_context_window() -> int:
    """Read context window from config, default 32000 for qwen2.5:3b."""
    return load_config().get("orchestrator", {}).get("context_window", 32_000)


# Kept as a module-level property for backward compatibility
MODEL_CONTEXT_WINDOW = _get_context_window()

# Compact when messages exceed this fraction of the context window
COMPACT_THRESHOLD = 0.75  # ~24,000 tokens
CRITICAL_THRESHOLD = 0.92  # ~29,440 tokens


def estimate_tokens(text: str) -> int:
    """Estimate token count from character count (~4 chars/token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_messages_tokens(messages: list[dict]) -> int:
    """Sum token estimates across a list of OpenAI-format message dicts."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, list):
            # Multimodal content (text + image_url blocks)
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total += estimate_tokens(block.get("text", ""))
                else:
                    total += 256  # rough image token estimate
        else:
            total += estimate_tokens(str(content))
        # Per-message overhead (~4 tokens for role + formatting)
        total += 4
    return total


def context_fraction(messages: list[dict]) -> float:
    """Return what fraction of the context window the messages occupy."""
    return estimate_messages_tokens(messages) / MODEL_CONTEXT_WINDOW


def needs_compaction(messages: list[dict]) -> bool:
    """Return True if messages exceed the compaction threshold."""
    return context_fraction(messages) >= COMPACT_THRESHOLD
