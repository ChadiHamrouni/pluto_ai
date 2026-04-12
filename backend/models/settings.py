from __future__ import annotations

from pydantic import BaseModel


class AgentModels(BaseModel):
    orchestrator: str
    compactor: str
