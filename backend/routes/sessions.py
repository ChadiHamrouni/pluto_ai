"""Session management endpoints: create, list, retrieve, delete."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from helpers.agents.session.session_store import (
    delete_session,
    get_session_messages,
    list_sessions,
    new_session,
    session_exists,
)
from helpers.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["sessions"])


@router.post(
    "/session",
    summary="Create a session",
    responses={200: {"content": {"application/json": {"example": {"session_id": "abc123"}}}}},
)
async def create_session():
    """Create a new server-side conversation session.

    Returns a `session_id` to pass in subsequent `POST /chat` or `POST /chat/stream` requests.
    Sessions persist conversation history and auto-generate a title from the first message.
    """
    sid = await new_session()
    logger.info("New session created: %s", sid)
    return {"session_id": sid}


@router.get("/sessions")
async def get_sessions():
    """Return all sessions with their titles, newest first."""
    sessions = await list_sessions()
    return {"sessions": sessions}


@router.get("/session/{session_id}/messages")
async def get_messages(session_id: str):
    """Return full message history for a session."""
    if not await session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_session_messages(session_id)
    return {"messages": messages}


@router.delete("/session/{session_id}")
async def remove_session(session_id: str):
    """Delete a session and all its messages."""
    if not await session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    await delete_session(session_id)
    return {"ok": True}
