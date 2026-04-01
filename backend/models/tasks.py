"""Pydantic models for task management tool inputs and outputs."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

TaskStatus = Literal["todo", "in_progress", "done"]
TaskPriority = Literal["low", "medium", "high", "urgent"]


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    status: TaskStatus = "todo"
    priority: TaskPriority = "medium"
    due_date: Optional[str] = Field(default=None, description="ISO-8601 date e.g. 2026-04-01")
    tags: list[str] = Field(default_factory=list)
    project: str = Field(default="", max_length=100)

    @field_validator("due_date", mode="before")
    @classmethod
    def empty_string_to_none(cls, v: str | None) -> str | None:
        return None if v == "" else v


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[str] = None
    tags: Optional[list[str]] = None
    project: Optional[str] = Field(default=None, max_length=100)


class TaskOut(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    due_date: Optional[str]
    tags: list[str]
    project: str
    created_at: str
    completed_at: Optional[str]

    @classmethod
    def from_row(cls, row: dict) -> "TaskOut":
        import json
        tags = row.get("tags", "[]")
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except Exception:
                tags = []
        return cls(
            id=row["id"],
            title=row["title"],
            description=row.get("description", ""),
            status=row.get("status", "todo"),
            priority=row.get("priority", "medium"),
            due_date=row.get("due_date"),
            tags=tags,
            project=row.get("project", ""),
            created_at=row.get("created_at", ""),
            completed_at=row.get("completed_at"),
        )
