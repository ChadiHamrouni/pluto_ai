"""Shared Pydantic result models used across handlers, runner, and routes."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AgentRunResult(BaseModel):
    """Result of a single agent run (runner.py)."""
    response: str
    tools_used: list[str] = Field(default_factory=list)
    agents_trace: list[str] = Field(default_factory=list)


class HandlerResult(BaseModel):
    """Result returned by file_handler and text_handler."""
    response: str
    elapsed: float
    tools_used: list[str] = Field(default_factory=list)
    agents_trace: list[str] = Field(default_factory=list)


class SlidePaths(BaseModel):
    """Paths produced for a Marp presentation."""
    md_path: str
    pdf_path: str


class LoopCreated(BaseModel):
    """Result of create_loop()."""
    task_id: str
    loop: object  # AutonomousLoop — kept as object to avoid circular import

    model_config = {"arbitrary_types_allowed": True}
