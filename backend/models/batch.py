"""Pydantic models for batch tool call inputs.

The OpenAI Agents SDK requires strict JSON schemas — bare dict/Any types are
rejected. These models define the per-item schema for each batch tool.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EventSpec(BaseModel):
    title: str = Field(..., description="Event title")
    start_time: str = Field(..., description="Local ISO-8601 without offset, e.g. '2026-04-21T09:00:00'")
    end_time: str = Field("", description="Local ISO-8601 end time without offset (optional)")
    description: str = Field("", description="Optional notes")
    location: str = Field("", description="Optional place or URL")
    recurrence: str = Field("", description="'' | 'daily' | 'weekly'")


class ReminderSpec(BaseModel):
    title: str = Field(..., description="What to remind the user about")
    remind_at: str = Field(..., description="Local ISO-8601 without offset, e.g. '2026-04-21T09:00:00'")
    recurrence: str = Field("", description="'' | 'daily' | 'weekly' | 'monthly'")


class TaskSpec(BaseModel):
    title: str = Field(..., description="Task title")
    category: str = Field("personal", description="groceries | work | career | finance | health | personal | home")
    description: str = Field("", description="Optional longer description")
    status: str = Field("todo", description="todo | in_progress | done")
    priority: str = Field("medium", description="low | medium | high | urgent")
    due_date: str = Field("", description="ISO-8601 date, e.g. '2026-04-30'")
    tags: str = Field("", description="Comma-separated tags")


class NoteSpec(BaseModel):
    title: str = Field(..., description="Unique descriptive title used as filename")
    content: str = Field(..., description="Full markdown body")
    category: str = Field("personal", description="teaching | research | career | personal | ideas")
    tags: str = Field("", description="Comma-separated tags")
