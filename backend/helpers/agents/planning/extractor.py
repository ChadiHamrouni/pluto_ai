"""Pre-extraction pass for multi-action prose inputs.

Converts free-form text like:
  "schedule a dentist Tuesday 2pm, a haircut Wednesday morning, and remind me to call mom Friday"

into a normalised structured list:
  [
    {"type": "event",    "title": "dentist",  "when": "Tuesday 2pm"},
    {"type": "event",    "title": "haircut",  "when": "Wednesday morning"},
    {"type": "reminder", "title": "call mom", "when": "Friday"},
  ]

This list is injected as a structured context block before the main agent run,
so the model doesn't need to re-parse the prose — it just maps each item to
the appropriate batch tool call.

Trigger heuristic (checked in message_builder before routing):
  len(message) > threshold  OR  message contains multi-action keywords
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from helpers.agents.execution.ollama_client import get_ollama_base_url
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

# Patterns that suggest multiple distinct actions in one message.
_MULTI_ACTION_RE = re.compile(
    r"\b(and\s+(also\s+)?remind|then\s+remind|,\s*remind|"
    r"and\s+(also\s+)?schedule|then\s+schedule|,\s*schedule|"
    r"and\s+(also\s+)?create|then\s+create|,\s*create|"
    r"and\s+(also\s+)?add|then\s+add|,\s*add)\b",
    re.IGNORECASE,
)

_ITEM_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "type":  {"type": "string", "enum": ["event", "reminder", "task", "note"]},
        "title": {"type": "string"},
        "when":  {"type": "string"},
    },
    "required": ["type", "title"],
}

_EXTRACT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": _ITEM_SCHEMA,
        }
    },
    "required": ["items"],
}

_SYSTEM_PROMPT = """\
You are a structured extraction assistant.
Given a user message that contains multiple actions, extract each distinct action as a JSON item.

For each item output:
  - type: "event" for calendar events, "reminder" for reminders/notifications,
           "task" for to-dos, "note" for notes to save
  - title: concise title (e.g. "dentist appointment")
  - when: the time expression exactly as the user stated it (e.g. "Tuesday 2pm", "next Friday")
          Leave when="" if no time was given.

Output ONLY the JSON object with an "items" array. No prose, no markdown fences.
"""


def should_extract(message: str, threshold_chars: int = 100) -> bool:
    """Return True if the message looks like it contains multiple actions."""
    if len(message) > threshold_chars and _MULTI_ACTION_RE.search(message):
        return True
    return False


async def extract_items(message: str, context_block: str, timeout: int = 15) -> list[dict[str, Any]]:
    """Run the extractor model and return the list of extracted action items.

    Returns [] on failure so the caller can proceed without the extraction.
    """
    cfg = load_config()
    model = cfg.get("extractor", {}).get("model", "qwen2.5:1.5b")
    base_url = get_ollama_base_url()

    prompt = f"{context_block}\n\nUser message: {message}"

    payload = {
        "model": model,
        "prompt": prompt,
        "system": _SYSTEM_PROMPT,
        "stream": False,
        "format": _EXTRACT_SCHEMA,
        "options": {"temperature": 0.0},
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}/api/generate", json=payload)
            resp.raise_for_status()
            raw = resp.json().get("response", "{}")
            data = json.loads(raw)
            items = data.get("items", [])
            if not isinstance(items, list):
                return []
            logger.info("Extractor found %d item(s) in message", len(items))
            return items
    except Exception as exc:
        logger.warning("Extractor failed (%s) — skipping pre-extraction", exc)
        return []


def format_extracted_context(items: list[dict[str, Any]]) -> str:
    """Render extracted items as a compact context block for prompt injection."""
    if not items:
        return ""
    lines = ["## Extracted actions"]
    for i, item in enumerate(items, 1):
        when = f' at {item["when"]}' if item.get("when") else ""
        lines.append(f"{i}. [{item['type']}] {item['title']}{when}")
    lines.append(
        "\nUse the appropriate batch tool (schedule_events / create_reminders / create_tasks / create_notes) "
        "to handle all items above in as few tool calls as possible."
    )
    return "\n".join(lines)
