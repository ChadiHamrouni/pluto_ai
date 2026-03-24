"""Streaming chat endpoint: POST /chat/stream (SSE, text-only)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from handlers.text_handler import text_handler_streamed
from helpers.agents.session.session_store import (
    append_turn,
    get_history,
    session_exists,
    update_session_title,
)
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/commands")
async def list_commands():
    """Return the slash command registry for the frontend autocomplete menu."""
    from helpers.agents.routing.command_parser import COMMAND_REGISTRY

    return [{"cmd": c["cmd"], "desc": c["desc"]} for c in COMMAND_REGISTRY]


@router.post(
    "/stream",
    summary="Stream a response (SSE)",
    response_description="Server-Sent Events stream.",
    responses={
        200: {
            "description": "SSE stream. Content-Type: text/event-stream.",
            "content": {
                "text/event-stream": {
                    "example": (
                        'event: token\ndata: {"delta": "The "}\n\n'
                        'event: token\ndata: {"delta": "answer is 42."}\n\n'
                        "event: tool_call\ndata: "
                        '{"tool": "web_search", "arguments": "{\\"query\\": \\".\\"}"}\\n\\n'
                        'event: agent_handoff\ndata: {"agent": "ResearchAgent"}\n\n'
                        "event: done\ndata: "
                        '{"response": "The answer is 42.", "tools_used": ["web_search"],'
                        ' "agents_trace": ["Orchestrator", "ResearchAgent"]}\n\n'
                    )
                }
            },
        },
        400: {"description": "File attachments are not supported for streaming."},
        401: {"description": "Missing or invalid access token."},
    },
)
async def chat_stream(
    message: str = Form(default="", description="The user's message."),
    session_id: str = Form(default="", description="Session ID from `POST /chat/session`."),
    attachments: List[UploadFile] = File(
        default=[], description="Not supported — use POST /chat for file attachments."
    ),
):
    """Stream a response as Server-Sent Events.

    Each event has the format: `event: <type>\\ndata: <json>\\n\\n`

    Event types:
    - **token** — `{"delta": "..."}` — partial text chunk
    - **tool_call** — `{"tool": "...", "arguments": "..."}` — a tool was invoked
    - **agent_handoff** — `{"agent": "..."}` — routing transferred to a specialist agent
    - **done** — `{"response": "...", "tools_used": [...], "agents_trace": [...]}` — run complete
    - **file_url** — `{"file_url": "/files/..."}` — a file was generated (slides, plot)
    - **error** — `{"message": "..."}` — unrecoverable error

    File attachments are not supported in this endpoint. Use `POST /chat` instead.
    """
    logger.info(
        "POST /chat/stream — session='%s' message=%r",
        session_id or "(none)",
        message[:80] if message else "",
    )

    window = load_config().get("orchestrator", {}).get("history_window", 20)

    exists = session_id and await session_exists(session_id)
    if exists:
        history = await get_history(session_id, max_turns=window)
    else:
        history = []

    if attachments and any(a.filename for a in attachments):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File attachments are not supported with streaming. Use POST /chat instead.",
        )

    _session_id = session_id
    _exists = exists
    _history = history
    _message = message

    async def event_generator():
        full_response = ""
        tools_used: list = []
        agents_trace: list = []

        try:
            async for event in text_handler_streamed(message, _history):
                event_type = event.get("event", "")
                data = event.get("data", {})

                if event_type == "token":
                    full_response += data.get("delta", "")
                elif event_type == "done":
                    full_response = data.get("response", full_response)
                    tools_used = data.get("tools_used", [])
                    agents_trace = data.get("agents_trace", [])

                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

            file_url = None
            history_response = full_response
            m = re.search(r"[\w/\\.:+-]+\.(?:pdf|md)", full_response)
            if m:
                file_url = f"/files/{Path(m.group(0)).name}"
                history_response = "Presentation generated successfully."

            if _session_id and _exists:
                await append_turn(
                    _session_id,
                    _message,
                    history_response,
                    assistant_metadata={
                        "tools_used": tools_used,
                        "agents_trace": agents_trace,
                    },
                )
                if not _history and _message:
                    title = _message[:50] + ("…" if len(_message) > 50 else "")
                    await update_session_title(_session_id, title)

            if file_url:
                yield f"event: file_url\ndata: {json.dumps({'file_url': file_url})}\n\n"

        except Exception as exc:
            logger.exception("Stream error")
            yield f"event: error\ndata: {json.dumps({'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
