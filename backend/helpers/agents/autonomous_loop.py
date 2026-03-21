"""Autonomous plan-and-execute loop.

Architecture:
1. Planner agent decomposes the task into steps (JSON array)
2. Executor agent runs each step with ReAct (think → act → observe)
3. On step failure: retry up to max_retries with revised instructions
4. SSE events pushed to the frontend via a callback

Usage:
    loop = AutonomousLoop(task_id, task, on_event)
    plan = await loop.run()
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Callable

from agents import Runner

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
from models.plan import ExecutionPlan, PlanStep
from models.results import LoopCreated
from my_agents.executor_agent import get_executor_agent, get_last_step_result, reset_step_result
from my_agents.planner_agent import get_planner_agent

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
            created_at=datetime.utcnow().isoformat(),
        )

    def cancel(self) -> None:
        self._cancelled = True

    def _push(self, event_type: str, data: dict | None = None) -> None:
        payload = {"type": event_type, "task_id": self.task_id, "plan": self.plan.model_dump()}
        if data:
            payload.update(data)
        try:
            self.on_event(payload)
        except Exception as exc:
            logger.warning("SSE push failed: %s", exc)

    async def _create_plan(self) -> list[PlanStep]:
        """Ask the planner to decompose the task into steps."""
        planner = get_planner_agent()
        messages = [{"role": "user", "content": f"Task: {self.task}"}]
        try:
            result = await Runner.run(starting_agent=planner, input=messages)
            raw = (result.final_output or "").strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                parts = raw.split("```")
                raw = parts[1] if len(parts) > 1 else raw
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            steps_data = json.loads(raw)
            if not isinstance(steps_data, list):
                raise ValueError("Planner did not return a list")
            return [
                PlanStep(id=s["id"], description=s["description"])
                for s in steps_data
                if isinstance(s, dict) and "id" in s and "description" in s
            ]
        except Exception as exc:
            logger.error("Planning failed: %s", exc)
            return []

    async def _execute_step(self, step: PlanStep, previous_results: list[str]) -> dict:
        """Run a single step through the executor agent."""
        executor = get_executor_agent()
        reset_step_result()

        context = f"Task: {self.task}\n\nFull plan:\n"
        for s in self.plan.steps:
            status = s.status
            context += f"  Step {s.id}: {s.description} [{status}]\n"

        if previous_results:
            context += "\nPrevious step results:\n"
            for r in previous_results:
                context += f"  - {r}\n"

        context += f"\nNow execute step {step.id}: {step.description}"

        messages = [{"role": "user", "content": context}]
        try:
            await Runner.run(starting_agent=executor, input=messages)
        except Exception as exc:
            logger.warning("Executor run raised: %s", exc)

        return get_last_step_result()

    async def run(self) -> ExecutionPlan:
        start_time = time.monotonic()

        # Phase 1: Planning
        self.plan.status = "planning"
        self._push("planning_started")

        steps = await self._create_plan()
        if not steps:
            self.plan.status = "failed"
            self._push("plan_failed", {"error": "Planner returned no steps"})
            return self.plan

        self.plan.steps = steps
        self.plan.status = "executing"
        self._push("plan_created")

        # Phase 2: Execute each step
        previous_results: list[str] = []

        for step in self.plan.steps:
            # Safety checks
            if self._cancelled:
                self.plan.status = "paused"
                self._push("cancelled")
                return self.plan

            elapsed = time.monotonic() - start_time
            if elapsed > self.max_duration:
                self.plan.status = "failed"
                self._push("timeout", {"error": f"Exceeded {self.max_duration}s time limit"})
                return self.plan

            if self.plan.iterations >= self.max_iterations:
                self.plan.status = "failed"
                self._push("max_iterations", {"error": "Exceeded max iterations"})
                return self.plan

            # Execute step with retries
            step.status = "in_progress"
            self.plan.current_step = step.id
            self._push("step_started", {"step_id": step.id})

            result = None
            for attempt in range(self.max_retries + 1):
                self.plan.iterations += 1
                result = await self._execute_step(step, previous_results)

                if result["success"]:
                    break

                step.retry_count = attempt + 1
                if attempt < self.max_retries:
                    logger.info(
                        "Step %d failed (attempt %d/%d): %s — retrying",
                        step.id,
                        attempt + 1,
                        self.max_retries + 1,
                        result["error"],
                    )
                    await asyncio.sleep(0.5)

            if result and result["success"]:
                step.status = "completed"
                step.result = result["summary"]
                previous_results.append(f"Step {step.id} ({step.description}): {result['summary']}")
            else:
                step.status = "failed"
                step.error = result["error"] if result else "Unknown error"
                previous_results.append(f"Step {step.id} FAILED: {step.error}")
                logger.warning("Step %d permanently failed: %s", step.id, step.error)

            self._push("step_completed", {"step_id": step.id})

        # Final status
        failed = [s for s in self.plan.steps if s.status == "failed"]
        self.plan.status = "failed" if failed else "completed"
        self._push("completed" if not failed else "completed_with_failures")
        return self.plan


# Registry of running loops (task_id → AutonomousLoop)
_active_loops: dict[str, AutonomousLoop] = {}


def create_loop(task: str, on_event: Callable[[dict], None]) -> LoopCreated:
    """Create a new autonomous loop and register it."""
    task_id = str(uuid.uuid4())
    loop = AutonomousLoop(task_id, task, on_event)
    _active_loops[task_id] = loop
    return LoopCreated(task_id=task_id, loop=loop)


def get_loop(task_id: str) -> AutonomousLoop | None:
    return _active_loops.get(task_id)


def remove_loop(task_id: str) -> None:
    _active_loops.pop(task_id, None)
