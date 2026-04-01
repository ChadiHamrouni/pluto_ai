"""Autonomous ReAct loop.

Architecture (collapsed single-agent):
  User task → Jarvis (ReAct, max_turns=20, streamed)
               ├─ token events → frontend in real time
               ├─ tool_call events → frontend in real time
               └─ done → final response

Replaces the old Planner → Executor → Synthesizer pipeline (3 agents,
N+2 LLM calls). Now: 1 agent, N LLM turns, parallel tool execution when
the model emits multiple tool calls in a single turn.

SSE event contract (unchanged from before):
  update  → {"type": "tool_call"|"token"|"done"|"error", "task_id": ..., ...}
  done    → {"type": "__done__", "task_id": ..., "plan": {...}}
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from agents import RunConfig, Runner

from helpers.agents.execution.event_parser import process_stream_event
from helpers.agents.routing.prompt_utils import _build_context_block
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from models.plan import ExecutionPlan, PlanStep
from models.results import LoopCreated

logger = get_logger(__name__)

_RUN_CONFIG = RunConfig(tracing_disabled=True)


class AutonomousLoop:
    def __init__(self, task_id: str, task: str, on_event: Callable[[dict], None]):
        self.task_id = task_id
        self.task = task
        self.on_event = on_event
        self._cancelled = False
        cfg = load_config().get("autonomous", {})
        self.max_turns: int = cfg.get("max_turns", 20)
        self.max_duration: float = cfg.get("max_duration_seconds", 300)
        # Minimal plan object — kept for API/frontend compatibility
        self.plan = ExecutionPlan(
            task_id=task_id,
            task=task,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def cancel(self) -> None:
        self._cancelled = True

    def _push(self, event_type: str, extra: dict | None = None) -> None:
        payload: dict = {
            "type": event_type,
            "task_id": self.task_id,
            "plan": self.plan.model_dump(),
        }
        if extra:
            payload.update(extra)
        try:
            self.on_event(payload)
        except Exception as exc:
            logger.warning("SSE push failed: %s", exc)

    async def run(self) -> ExecutionPlan:
        from my_agents.single import get_single_agent

        start_time = time.monotonic()
        self.plan.status = "executing"
        self._push("planning_started")  # signal frontend the task has begun

        # Inject date/time context into the task prompt so the agent can
        # resolve relative dates ("tomorrow", "next Monday", etc.)
        context_block = _build_context_block()
        user_input = f"{context_block}\n\n---\n\nTask: {self.task}"

        agent = get_single_agent()
        full_response = ""
        tools_used: list[str] = []
        agents_seen: list[str] = [agent.name]
        step_counter = 0

        try:
            streamed = Runner.run_streamed(
                starting_agent=agent,
                input=user_input,
                run_config=_RUN_CONFIG,
                max_turns=self.max_turns,
            )

            async for event in streamed.stream_events():
                if self._cancelled:
                    self.plan.status = "paused"
                    self._push("cancelled")
                    return self.plan

                if time.monotonic() - start_time > self.max_duration:
                    self.plan.status = "failed"
                    self._push("timeout", {"error": f"Exceeded {self.max_duration}s limit"})
                    return self.plan

                # Reuse the existing event parser — handles tokens, tool calls, handoffs
                full_response, sse_events = process_stream_event(
                    event, full_response, tools_used, agents_seen
                )

                for sse in sse_events:
                    ev_type = sse.get("event")

                    if ev_type == "token":
                        self._push("token", {"delta": sse["data"]["delta"]})

                    elif ev_type == "tool_call":
                        tool_name = sse["data"]["tool"]
                        step_counter += 1
                        # Add a lightweight step to the plan for frontend visibility
                        step = PlanStep(
                            id=step_counter,
                            description=tool_name,
                            status="in_progress",
                        )
                        self.plan.steps.append(step)
                        self.plan.current_step = step_counter
                        self._push("step_started", {
                            "step_id": step_counter,
                            "tool": tool_name,
                            "arguments": sse["data"].get("arguments", ""),
                        })

                    elif ev_type == "agent_handoff":
                        self._push("agent_handoff", {"agent": sse["data"]["agent"]})

            # Mark all steps completed now that streaming finished
            for step in self.plan.steps:
                if step.status == "in_progress":
                    step.status = "completed"

        except Exception as exc:
            logger.exception("ReAct loop failed for task %s: %s", self.task_id, exc)
            self.plan.status = "failed"
            self._push("error", {"error": str(exc)})
            return self.plan

        self.plan.final_response = full_response or "Done."
        self.plan.status = "completed"
        self._push("completed")
        return self.plan


# ── Registry ──────────────────────────────────────────────────────────────────

_active_loops: dict[str, AutonomousLoop] = {}


def create_loop(task: str, on_event: Callable[[dict], None]) -> LoopCreated:
    task_id = str(uuid.uuid4())
    loop = AutonomousLoop(task_id, task, on_event)
    _active_loops[task_id] = loop
    return LoopCreated(task_id=task_id, loop=loop)


def get_loop(task_id: str) -> AutonomousLoop | None:
    return _active_loops.get(task_id)


def remove_loop(task_id: str) -> None:
    _active_loops.pop(task_id, None)
