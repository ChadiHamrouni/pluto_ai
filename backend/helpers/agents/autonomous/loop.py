"""Autonomous plan-and-execute loop.

Architecture:
1. Planner decomposes the task into PlanStep objects (structured output)
2. Executor runs each step via Runner.run_streamed — tool calls are intercepted
   in real-time so links are pushed to the frontend as they are visited
3. On step failure: retry up to max_retries with error context
4. Synthesiser produces a coherent final answer from all step summaries
5. SSE events are pushed to the frontend via on_event callback throughout
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from helpers.agents.autonomous.phases import (
    build_step_context,
    execute_step,
    run_planning,
    synthesise,
)
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from models.plan import ExecutionPlan, PlanStep
from models.results import LoopCreated, StepResult
from my_agents.executor_agent import reset_executor_agent

logger = get_logger(__name__)


class AutonomousLoop:
    def __init__(self, task_id: str, task: str, on_event: Callable[[dict], None]):
        self.task_id = task_id
        self.task = task
        self.on_event = on_event
        self._cancelled = False
        cfg = load_config().get("autonomous", {})
        self.max_iterations: int = cfg.get("max_iterations", 50)
        self.max_duration: float = cfg.get("max_duration_seconds", 300)
        self.max_retries: int = cfg.get("max_retries_per_step", 2)
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

    async def _run_step_with_retries(
        self, step: PlanStep, previous_results: list[str]
    ) -> StepResult | None:
        for attempt in range(self.max_retries + 1):
            self.plan.iterations += 1
            context = build_step_context(self.task, self.plan, step, previous_results)

            def on_link(url: str) -> None:
                step.links = list({*step.links, url})
                self._push("step_link", {"step_id": step.id, "url": url})

            result = await execute_step(step, context, on_link)
            if result.success:
                return result
            step.retry_count = attempt + 1
            if attempt < self.max_retries:
                logger.info(
                    "Step %d failed (attempt %d/%d): %s — retrying",
                    step.id, attempt + 1, self.max_retries + 1, result.error,
                )
                await asyncio.sleep(0.5)
        return result  # last failed result

    async def run(self) -> ExecutionPlan:
        start_time = time.monotonic()
        reset_executor_agent()

        # Phase 1: Plan
        self.plan.status = "planning"
        self._push("planning_started")

        steps = await run_planning(self.task)
        if not steps:
            self.plan.status = "failed"
            self._push("plan_failed", {"error": "Planner returned no steps"})
            return self.plan

        self.plan.steps = steps
        self.plan.status = "executing"
        self._push("plan_created")

        # Phase 2: Execute
        previous_results: list[str] = []

        for step in self.plan.steps:
            if self._cancelled:
                self.plan.status = "paused"
                self._push("cancelled")
                return self.plan

            if time.monotonic() - start_time > self.max_duration:
                self.plan.status = "failed"
                self._push("timeout", {"error": f"Exceeded {self.max_duration}s limit"})
                return self.plan

            if self.plan.iterations >= self.max_iterations:
                self.plan.status = "failed"
                self._push("max_iterations", {"error": "Exceeded max iterations"})
                return self.plan

            step.status = "in_progress"
            self.plan.current_step = step.id
            self._push("step_started", {"step_id": step.id})

            step_result = await self._run_step_with_retries(step, previous_results)

            if step_result and step_result.success:
                step.status = "completed"
                step.result = step_result.summary
                step.links = step_result.links
                previous_results.append(
                    f"Step {step.id} ({step.description}): {step_result.summary}"
                )
            else:
                step.status = "failed"
                step.error = step_result.error if step_result else "Unknown error"
                step.links = step_result.links if step_result else []
                previous_results.append(f"Step {step.id} FAILED: {step.error}")
                logger.warning("Step %d permanently failed: %s", step.id, step.error)

            self._push("step_completed", {"step_id": step.id})

        # Phase 3: Synthesise
        self.plan.final_response = await synthesise(self.task, previous_results)

        failed = [s for s in self.plan.steps if s.status == "failed"]
        self.plan.status = "completed" if not failed else "failed"
        self._push("completed" if not failed else "completed_with_failures")
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
