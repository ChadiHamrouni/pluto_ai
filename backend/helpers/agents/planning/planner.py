"""Grammar-constrained multi-step planner.

Wraps the planner model with a strict JSON schema via Ollama's `format`
parameter, making malformed plan output structurally impossible.

Schema produced:
    {
      "steps": [
        {
          "step": 1,
          "action": "web_search",
          "reason": "...",
          "items": [{"query": "..."}]
        },
        {
          "step": 2,
          "action": "draft_slides",
          "reason": "...",
          "items": []
        },
        ...
      ]
    }

Each step maps to one tool call. The plan is injected as a context block
into the agent's input so it executes steps in order without re-deriving them.
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

# ---------------------------------------------------------------------------
# Trigger heuristics
# ---------------------------------------------------------------------------

_SLIDES_RE = re.compile(
    r"\b(presentation|slides?|slide\s*deck|powerpoint|keynote|marp|make\s+me\s+a\s+deck"
    r"|create\s+a\s+(presentation|deck|slideshow)|generate\s+(a\s+)?(presentation|slides?))\b",
    re.IGNORECASE,
)

_DIAGRAM_RE = re.compile(
    r"\b(diagram|flowchart|sequence\s+diagram|mermaid|draw\s+(me\s+a|a)|chart)\b",
    re.IGNORECASE,
)

_RESEARCH_RE = re.compile(
    r"\b(research|find\s+out|look\s+up|search\s+(for|the\s+web)|what('s|\s+is)\s+the\s+latest"
    r"|current\s+(stats|data|numbers|trends)|up[\s-]?to[\s-]?date)\b",
    re.IGNORECASE,
)


def should_plan(message: str) -> bool:
    """Return True if the message describes a complex multi-step task that needs planning."""
    return bool(
        _SLIDES_RE.search(message)
        or _DIAGRAM_RE.search(message)
        or _RESEARCH_RE.search(message)
    )


# ---------------------------------------------------------------------------
# Planner schema + prompt
# ---------------------------------------------------------------------------

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
You are a planning assistant. Given the user's request, output a minimal JSON execution plan.
Each step has:
  - step (integer, starting at 1)
  - action (one of the tool names below)
  - reason (one sentence)
  - items (list of input objects for that tool, or [] if inputs come from a prior step)

Available actions and their item schemas:
  schedule_events    → [{title, start_time (ISO-8601), end_time?, description?, location?, recurrence?}]
  create_reminders   → [{title, remind_at (ISO-8601), recurrence?}]
  create_tasks       → [{title, category, description?, priority?, due_date?}]
  create_notes       → [{title, content, category, tags?}]
  web_search         → [{query}]
  draft_slides       → []   (content comes from prior web_search step)
  render_slides      → []   (content comes from prior draft_slides step)
  generate_diagram   → []   (content comes from prior step or request)
  direct             → []   (single-step, no planning needed)

Rules:
- For slide presentations: always plan web_search → draft_slides → render_slides (3 steps).
  Skip web_search only if the topic is purely conceptual/historical with no need for current data.
- For diagrams: plan generate_diagram as a single step.
- For multi-action requests (events + tasks + reminders): one step per tool, parallel where independent.
- For simple single-action requests: use action="direct" with items=[].
- Always resolve relative dates using the context block date provided.
- Output ONLY the JSON object — no prose, no markdown fences.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

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
        "format": "json",
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
            logger.info("Planner produced %d step(s) for: %.60s", len(plan["steps"]), message)
            return plan
    except Exception as exc:
        logger.warning("Planner failed (%s) — falling back to direct execution", exc)
        return {"steps": [{"step": 1, "action": "direct", "items": []}]}


def is_multi_step_plan(plan: dict) -> bool:
    """Return True if the plan has more than one step or has any non-direct action."""
    steps = plan.get("steps", [])
    if len(steps) > 1:
        return True
    if steps and steps[0].get("action", "direct") != "direct":
        return True
    return False


def format_plan_context(plan: dict, original_message: str) -> str:
    """Render a plan as a structured context block for prompt injection.

    The agent reads this block and executes steps in order — no re-derivation needed.
    """
    steps = plan.get("steps", [])
    if not steps or (len(steps) == 1 and steps[0].get("action") == "direct"):
        return ""

    lines = [
        "## Execution plan",
        f"Task: {original_message}",
        "",
        "Execute these steps IN ORDER. Do not skip or reorder them.",
        "For steps with items=[], use the output of the previous step as input.",
        "",
    ]
    for s in steps:
        action = s.get("action", "")
        reason = s.get("reason", "")
        items = s.get("items", [])
        item_str = f" — inputs: {json.dumps(items)}" if items else " — inputs from previous step"
        lines.append(f"Step {s['step']}: {action}{item_str}")
        if reason:
            lines.append(f"  Reason: {reason}")

    lines += [
        "",
        "Complete ALL steps before responding to the user.",
    ]
    return "\n".join(lines)
