from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from agents.orchestrator import run_orchestrator
from helpers.routes.dependencies import get_current_user
from helpers.core.logger import get_logger
from models.chat import ChatRequest, ChatResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, _user: dict = Depends(get_current_user)):
    """Send a message to the AI assistant and receive a response."""
    try:
        response_text = await run_orchestrator(
            message=request.message,
            history=request.history,
        )
    except Exception as exc:
        logger.error("Chat endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Orchestrator error: {exc}")

    return ChatResponse(response=response_text)
