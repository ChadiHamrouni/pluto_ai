from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from handlers.file_handler import file_handler
from handlers.text_handler import text_handler, text_handler_streamed
from helpers.agents.session_store import (
    append_turn,
    delete_session,
    get_history,
    get_session_messages,
    list_sessions,
    new_session,
    session_exists,
    update_session_title,
)
from helpers.core.logger import get_logger
from helpers.routes.dependencies import get_current_user
from models.chat import Attachment, ChatResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".pdf", ".txt"}

_MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


@router.post(
    "/session",
    tags=["chat"],
    summary="Create a session",
    responses={200: {"content": {"application/json": {"example": {"session_id": "abc123"}}}}},
)
async def create_session(_user: dict = Depends(get_current_user)):
    """Create a new server-side conversation session.

    Returns a `session_id` to pass in subsequent `POST /chat` or `POST /chat/stream` requests.
    Sessions persist conversation history and auto-generate a title from the first message.
    """
    sid = await new_session()
    logger.info("New session created: %s", sid)
    return {"session_id": sid}


@router.get("/sessions", tags=["chat"])
async def get_sessions(_user: dict = Depends(get_current_user)):
    """Return all sessions with their titles, newest first."""
    sessions = await list_sessions()
    return {"sessions": sessions}


@router.get("/session/{session_id}/messages", tags=["chat"])
async def get_messages(session_id: str, _user: dict = Depends(get_current_user)):
    """Return full message history for a session."""
    if not await session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    messages = await get_session_messages(session_id)
    return {"messages": messages}


@router.delete("/session/{session_id}", tags=["chat"])
async def remove_session(session_id: str, _user: dict = Depends(get_current_user)):
    """Delete a session and all its messages."""
    if not await session_exists(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    await delete_session(session_id)
    return {"ok": True}


@router.post(
    "",
    response_model=ChatResponse,
    summary="Send a message",
    response_description="Assistant reply with tool/agent metadata.",
    responses={
        200: {
            "description": "Successful response from the agent system.",
            "content": {
                "application/json": {
                    "example": {
                        "response": (
                            "The James Webb Space Telescope was"
                            " launched on 25 December 2021."
                        ),
                        "attachments": [],
                        "tools_used": ["web_search"],
                        "agents_trace": ["Orchestrator"],
                        "file_url": None,
                    }
                }
            },
        },
        415: {"description": "Unsupported attachment file type."},
        401: {"description": "Missing or invalid access token."},
        500: {"description": "Internal error — agent run failed."},
    },
)
async def chat(
    message: str = Form(
        default="",
        description=(
            "The user's message. Supports slash commands:"
            " `/note`, `/slides`, `/research`, `/calendar`."
        ),
    ),
    session_id: str = Form(
        default="",
        description="Session ID from `POST /chat/session`. Omit for a stateless one-off request.",
    ),
    attachments: List[UploadFile] = File(
        default=[],
        description=(
            "Optional files: images (jpg/png/webp/gif/bmp), PDF, or .txt."
            " First file is the primary attachment."
        ),
    ),
    _user: dict = Depends(get_current_user),
):
    """Send a message and receive a full response.

    The agent system will:
    1. Parse slash commands for deterministic routing
    2. Search personal memory and inject relevant facts
    3. Route to the appropriate specialist agent (or handle directly)
    4. Return the response with tool and agent metadata

    For token-by-token streaming, use `POST /chat/stream` instead.
    File attachments are not supported in the streaming endpoint.
    """
    logger.info(
        "POST /chat — session='%s' message=%r attachments=%d",
        session_id or "(none)",
        message[:80] if message else "",
        len(attachments),
    )

    from helpers.core.config_loader import load_config

    window = load_config().get("orchestrator", {}).get("history_window", 20)

    exists = session_id and await session_exists(session_id)
    if exists:
        history = await get_history(session_id, max_turns=window)
    else:
        history = []
        if session_id:
            logger.warning("Unknown session_id '%s' — proceeding without history", session_id)

    # Write all valid attachments to temp files
    temp_paths: list[Path] = []
    attachment_meta: list[Attachment] = []

    try:
        for upload in attachments:
            if not upload.filename:
                continue
            ext = Path(upload.filename).suffix.lower()
            if ext not in _SUPPORTED_EXTS:
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_SUPPORTED_EXTS)}",
                )
            data = await upload.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(data)
                tmp_path = Path(tmp.name)
            temp_paths.append(tmp_path)
            attachment_meta.append(
                Attachment(
                    filename=upload.filename,
                    mime_type=_MIME_MAP.get(ext, "application/octet-stream"),
                    size_bytes=len(data),
                )
            )

        primary = temp_paths[0] if temp_paths else None

        if primary:
            extra_context = ""
            if len(temp_paths) > 1:
                names = ", ".join(a.filename for a in attachment_meta[1:])
                extra_context = f"\n\n[Additional attached files: {names}]"
            full_message = message + extra_context
            handler_result = await file_handler(full_message, history, primary)
        else:
            handler_result = await text_handler(message, history)

        response_text = handler_result.response
        tools_used = handler_result.tools_used
        agents_trace = handler_result.agents_trace

        logger.info(
            "Response ready (%d chars) for session '%s'", len(response_text), session_id or "(none)"
        )

        # If the response contains a generated file path, expose it as a download URL.
        file_url: str | None = None
        history_response = response_text
        m = re.search(r"[\w/\\.:+-]+\.(?:pdf|md)", response_text)
        if m:
            file_url = f"/files/{Path(m.group(0)).name}"
            response_text = "Your presentation is ready."
            history_response = "Presentation generated successfully."

        # Persist this exchange and update the session title from the first message
        if session_id and exists:
            await append_turn(session_id, message, history_response)
            # Set title from the first user message if the history was empty before this turn
            if not history and message:
                title = message[:50] + ("…" if len(message) > 50 else "")
                await update_session_title(session_id, title)

        return ChatResponse(
            response=response_text,
            attachments=attachment_meta,
            tools_used=tools_used,
            agents_trace=agents_trace,
            file_url=file_url,
        )

    except HTTPException:
        raise
    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
    except Exception as exc:
        logger.exception("Chat endpoint unhandled error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    finally:
        for p in temp_paths:
            p.unlink(missing_ok=True)


@router.post(
    "/stream",
    tags=["chat"],
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
                        'event: tool_call\ndata: {"tool": "web_search",'
                        ' "arguments": "{\\"query\\": \\".\\"}"}\\n\\n'
                        'event: agent_handoff\ndata: {"agent": "ResearchAgent"}\n\n'
                        'event: done\ndata: {"response": "The answer is 42.",'
                        ' "tools_used": ["web_search"],'
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
    _user: dict = Depends(get_current_user),
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

    from helpers.core.config_loader import load_config

    window = load_config().get("orchestrator", {}).get("history_window", 20)

    exists = session_id and await session_exists(session_id)
    if exists:
        history = await get_history(session_id, max_turns=window)
    else:
        history = []

    # Reject attachments for now — streaming only supports text messages
    if attachments and any(a.filename for a in attachments):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File attachments are not supported with streaming. Use POST /chat instead.",
        )

    # Capture session state for the done-event callback
    _session_id = session_id
    _exists = exists
    _history = history
    _message = message

    async def event_generator():
        full_response = ""

        try:
            async for event in text_handler_streamed(message, _history):
                event_type = event.get("event", "")
                data = event.get("data", {})

                if event_type == "token":
                    full_response += data.get("delta", "")
                elif event_type == "done":
                    full_response = data.get("response", full_response)
                    data.get("tools_used", [])
                    data.get("agents_trace", [])

                yield f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

            # Detect file URLs in the response (slides, etc.)
            file_url = None
            history_response = full_response
            m = re.search(r"[\w/\\.:+-]+\.(?:pdf|md)", full_response)
            if m:
                file_url = f"/files/{Path(m.group(0)).name}"
                history_response = "Presentation generated successfully."

            # Persist this exchange
            if _session_id and _exists:
                await append_turn(_session_id, _message, history_response)
                if not _history and _message:
                    title = _message[:50] + ("…" if len(_message) > 50 else "")
                    await update_session_title(_session_id, title)

            # Final done event with file_url included
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
