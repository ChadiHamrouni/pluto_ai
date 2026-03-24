from __future__ import annotations

from pydantic import BaseModel


class AgentModels(BaseModel):
    orchestrator: str
    notes_agent: str
    slides_agent: str
    autonomous: str
