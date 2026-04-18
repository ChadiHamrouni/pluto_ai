"""Grammar-constrained multi-step planner.

Wraps qwen2.5:1.5b (the planner model) with a strict JSON schema via Ollama's
`format` parameter, making malformed plan output structurally impossible.

Schema produced:
    {
      "steps": [
        {
          "step": 1,
          "action": "schedule_events",   # tool name
          "reason": "...",               # short justification
          "items": [...]                 # payload — tool-specific list of objects
        },
        ...
      ]
    }

Each step maps to one tool call. The agent loop in runner.py reads this plan,
executes each step in order (updating TaskState), and skips steps whose items
have already been created (idempotency).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from helpers.agents.execution.ollama_client import get_ollama_base_url
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

# JSON schema enforced by Ollama's `format` parameter.
_PLAN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step":   {"type": "integer"},
                    "action": {"type": "string"},
                    "reason": {"type": "string"},
                    "items":  {"type": "array", "items": {"type": "object"}},
                },
                "required": ["step", "action", "items"],
            },
        }
    },
    "required": ["steps"],
}

_SYSTEM_PROMPT = """\
You are a planning assistant. Given the user's request, output a JSON execution plan.
Each step has:
  - step (integer, starting at 1)
  - action (tool name: schedule_events | create_reminders | create_tasks | create_notes | other)
  - reason (one sentence)
  - items (list of objects matching that tool's input schema)

For schedule_events items use: {title, start_time (local ISO-8601), end_time?, description?, location?, recurrence?}
For create_reminders items use: {title, remind_at (local ISO-8601), recurrence?}
For create_tasks items use: {title, category, description?, status?, priority?, due_date?, tags?}
For create_notes items use: {title, content, category, tags?}
For other single-step actions set action="direct" and items=[].

Today's date and time are provided in the user message context block. Always resolve relative dates.
Output ONLY the JSON object — no prose, no markdown fences.
"""


async def build_plan(message: str, context_block: str, timeout: int = 30) -> dict[str, Any]:
    """Call the planner model and return a validated plan dict.

    Falls back to {"steps": [{"step": 1, "action": "direct", "items": []}]} on
    any failure so the caller can always treat the result as a plan.
    """
    cfg = load_config()
    model = cfg.get("planner", {}).get("model", "qwen2.5:1.5b")
    base_url = get_ollama_base_url()

    prompt = f"{context_block}\n\nUser request: {message}"

    payload = {
        "model": model,
        "prompt": prompt,
        "system": _SYSTEM_PROMPT,
        "stream": False,
        "format": _PLAN_SCHEMA,
        "options": {"temperature": 0.0},
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base_url}/api/generate", json=payload)
            resp.raise_for_status()
            raw = resp.json().get("response", "{}")
            plan = json.loads(raw)
            if "steps" not in plan or not isinstance(plan["steps"], list):
                raise ValueError("Missing 'steps' array in plan")
            logger.info("Planner produced %d step(s) for: %s", len(plan["steps"]), message[:60])
            return plan
    except Exception as exc:
        logger.warning("Planner failed (%s) — falling back to direct execution", exc)
        return {"steps": [{"step": 1, "action": "direct", "items": []}]}


def is_multi_step_plan(plan: dict) -> bool:
    """Return True if the plan has more than one step or has any batch action."""
    steps = plan.get("steps", [])
    if len(steps) > 1:
        return True
    if steps and steps[0].get("action", "direct") != "direct":
        return True
    return False
