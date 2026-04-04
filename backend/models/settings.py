from __future__ import annotations

from pydantic import BaseModel


class AgentModels(BaseModel):
    orchestrator: str
    slides_agent: str
