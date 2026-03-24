"""Progressive context compaction with memory flush.

When the message history approaches the context window limit:
1. Identifies the oldest messages that push us over the threshold
2. Optionally extracts durable facts before discarding them
3. Summarises them into a single [Summary] system message
4. Returns a shorter message list that stays within budget
"""

from __future__ import annotations

import asyncio
import json

from openai import AsyncOpenAI

from helpers.agents.token_counter import (
    COMPACT_THRESHOLD,
    MODEL_CONTEXT_WINDOW,
    estimate_messages_tokens,
    estimate_tokens,
    needs_compaction,
)
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from helpers.tools.memory import get_db_path, insert_memory

logger = get_logger(__name__)

_SUMMARY_PROMPT = """You are summarising a conversation for an AI assistant's context window.

Summarise the following messages into ONE concise paragraph. Preserve:
- Key decisions and conclusions
- User preferences and facts about the user
- Any task context still in progress
- Important information the assistant was told

Discard: greetings, filler, resolved questions, repeated content.

Keep the summary under 200 words. Reply with ONLY the summary paragraph, no preamble."""

_EXTRACT_FACTS_PROMPT = """
You are extracting durable facts from a conversation before it is discarded.

Given these messages, extract any facts about the user worth remembering long-term.
Only extract genuinely useful facts (preferences, goals, personal details, recurring context).
Return a JSON array of objects with keys: content (string), category
(one of: teaching, research, career, personal, ideas), tags (array of strings).
If nothing is worth saving, return an empty array [].

Reply with ONLY the JSON array, no other text."""


async def _call_ollama(client: AsyncOpenAI, model: str, prompt: str, content: str) -> str:
    """Make a raw completion call to summarise or extract facts."""
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
            max_tokens=512,
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("Compaction LLM call failed: %s", exc)
        return ""


def _messages_to_text(messages: list[dict]) -> str:
    """Flatten messages to a readable text block for LLM summarisation."""
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") in ("text", "input_text")
            )
        lines.append(f"[{role.upper()}]: {content}")
    return "\n".join(lines)


async def _flush_facts_to_memory(client: AsyncOpenAI, model: str, old_messages: list[dict]) -> None:
    """Extract and persist durable facts from messages about to be compacted."""
    db_path = get_db_path()
    text = _messages_to_text(old_messages)
    raw = await _call_ollama(client, model, _EXTRACT_FACTS_PROMPT, text)
    if not raw:
        return

    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        facts = json.loads(raw)
        if not isinstance(facts, list):
            return
        valid_categories = load_config()["memory"]["categories"]
        for fact in facts:
            content = fact.get("content", "").strip()
            category = fact.get("category", "personal")
            tags = fact.get("tags", [])
            if not content or category not in valid_categories:
                continue
            tags_json = json.dumps(tags if isinstance(tags, list) else [])
            try:
                entry_id = insert_memory(db_path, content, category, tags_json)
                logger.info("Compaction flushed memory id=%d: %s", entry_id, content[:60])
            except Exception as exc:
                logger.warning("Failed to flush memory fact: %s", exc)
    except json.JSONDecodeError:
        logger.warning("Compaction fact extraction returned invalid JSON")


async def compact_history(
    messages: list[dict],
    client: AsyncOpenAI,
    model: str,
) -> list[dict]:
    """Compact messages if they exceed COMPACT_THRESHOLD of the context window.

    - Preserves the system prompt (first message)
    - Summarises the oldest non-system messages that push over budget
    - Flushes durable facts to memory before discarding
    - Returns a shorter list that fits within budget

    Args:
        messages: Full list of OpenAI-format message dicts.
        client:   AsyncOpenAI client pointing at Ollama.
        model:    Model name for summarisation calls.

    Returns:
        Possibly-compacted message list.
    """
    if not needs_compaction(messages):
        return messages

    logger.info(
        "Compacting context: %d tokens / %d window (%.0f%%)",
        estimate_messages_tokens(messages),
        MODEL_CONTEXT_WINDOW,
        estimate_messages_tokens(messages) / MODEL_CONTEXT_WINDOW * 100,
    )

    # Separate system prompt from conversation
    system_msgs = [m for m in messages if m.get("role") == "system"]
    conv_msgs = [m for m in messages if m.get("role") != "system"]

    target_tokens = int(MODEL_CONTEXT_WINDOW * COMPACT_THRESHOLD * 0.7)
    system_tokens = sum(estimate_tokens(m.get("content", "")) for m in system_msgs)
    budget = target_tokens - system_tokens

    # Find how many old messages to compact
    kept: list[dict] = []
    to_compact: list[dict] = []
    running = 0
    for msg in reversed(conv_msgs):
        msg_tokens = estimate_messages_tokens([msg])
        if running + msg_tokens <= budget:
            running += msg_tokens
            kept.insert(0, msg)
        else:
            to_compact.insert(0, msg)

    if not to_compact:
        # Nothing safe to compact — just return as-is
        return messages

    # Flush facts + summarise in parallel — both read the same messages
    text_to_summarise = _messages_to_text(to_compact)
    _, summary_text = await asyncio.gather(
        _flush_facts_to_memory(client, model, to_compact),
        _call_ollama(client, model, _SUMMARY_PROMPT, text_to_summarise),
    )

    if not summary_text:
        logger.warning("Compaction summary failed — keeping original messages")
        return messages

    summary_msg = {
        "role": "system",
        "content": f"[Summary of earlier conversation]\n{summary_text}",
    }

    compacted = system_msgs + [summary_msg] + kept
    logger.info(
        "Compacted %d messages → summary + %d kept (%d tokens → %d tokens)",
        len(to_compact),
        len(kept),
        estimate_messages_tokens(messages),
        estimate_messages_tokens(compacted),
    )
    return compacted
