from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel


class PlanStep(BaseModel):
    id: int
    description: str
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = "pending"
    result: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0


class ExecutionPlan(BaseModel):
    task_id: str
    task: str
    steps: List[PlanStep] = []
    current_step: int = 0
    status: Literal["planning", "executing", "completed", "failed", "paused"] = "planning"
    created_at: str = ""
    iterations: int = 0
