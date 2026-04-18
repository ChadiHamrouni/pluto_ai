"""Slot-filling task state for multi-step agent runs.

Maintains an explicit JSON checklist across tool calls so the model can read
what's done vs. remaining instead of re-deriving it from conversation history.

State is serialised to a compact JSON block and injected as a system-level
context prefix before each tool-call turn in multi-step runs.

Example state:
    {
      "task": "schedule 5 standup events Mon-Fri 9am",
      "completed": [{"id": "e1", "title": "Monday standup", "action": "schedule_events"}],
      "remaining": [{"title": "Tuesday standup"}, ...],
      "blocked": []
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskState:
    task: str = ""
    completed: list[dict[str, Any]] = field(default_factory=list)
    remaining: list[dict[str, Any]] = field(default_factory=list)
    blocked: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------ #
    # Mutation helpers                                                     #
    # ------------------------------------------------------------------ #

    def mark_done(self, item: dict[str, Any]) -> None:
        """Move an item from remaining → completed."""
        title = item.get("title", "")
        self.remaining = [r for r in self.remaining if r.get("title") != title]
        if not any(c.get("title") == title for c in self.completed):
            self.completed.append(item)

    def add_remaining(self, items: list[dict[str, Any]]) -> None:
        for it in items:
            if not any(r.get("title") == it.get("title") for r in self.remaining):
                self.remaining.append(it)

    def record_tool_result(self, tool_name: str, result_text: str) -> None:
        """Parse a batch tool result string and update completed/remaining."""
        lines = result_text.splitlines()
        for line in lines:
            line = line.strip()
            if line.startswith("✓") or line.startswith("~"):
                # Formats: "  ✓ [42] Event title at ..."  or  "  ~ [42] skipped"
                bracket_start = line.find("[")
                bracket_end = line.find("]", bracket_start)
                id_val = line[bracket_start + 1:bracket_end] if bracket_start != -1 else ""
                rest = line[bracket_end + 1:].strip() if bracket_end != -1 else line
                title = rest.split(" at ")[0].strip() if " at " in rest else rest.split("→")[0].strip()
                self.mark_done({"id": id_val, "title": title, "action": tool_name})

    # ------------------------------------------------------------------ #
    # Serialisation                                                        #
    # ------------------------------------------------------------------ #

    def to_context_block(self) -> str:
        """Render the state as a compact system context block for prompt injection."""
        if not self.task and not self.completed and not self.remaining:
            return ""
        payload = {
            "task": self.task,
            "completed": self.completed,
            "remaining": self.remaining,
        }
        if self.blocked:
            payload["blocked"] = self.blocked
        return "## Task progress\n```json\n" + json.dumps(payload, indent=2) + "\n```"

    def is_complete(self) -> bool:
        return len(self.remaining) == 0 and (len(self.completed) > 0 or not self.task)

    def has_work(self) -> bool:
        return bool(self.task or self.remaining)

    @classmethod
    def from_plan(cls, task_description: str, plan: dict) -> "TaskState":
        """Initialise a TaskState from a planner output dict."""
        state = cls(task=task_description)
        for step in plan.get("steps", []):
            action = step.get("action", "direct")
            if action == "direct":
                continue
            for item in step.get("items", []):
                state.remaining.append({**item, "_action": action})
        return state
