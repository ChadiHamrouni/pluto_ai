from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


class StepItem(BaseModel):
    """Lightweight step used by the planner agent's structured output."""
    id: int
    tool: str   # exact tool name the executor must call (e.g. "web_search")
    description: str


class PlanOutput(BaseModel):
    """Structured output returned by the planner agent."""
    steps: list[StepItem]


class PlanStep(BaseModel):
    id: int
    description: str
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = "pending"
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    links: List[str] = []


class ExecutionPlan(BaseModel):
    task_id: str
    task: str
    steps: List[PlanStep] = []
    current_step: int = 0
    status: Literal["planning", "executing", "completed", "failed", "paused"] = "planning"
    created_at: str = ""
    iterations: int = 0
    final_response: Optional[str] = None
