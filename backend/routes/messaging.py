"""Chat messaging endpoint: POST /chat (non-streaming, supports file attachments)."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from handlers.file_handler import file_handler
from handlers.text_handler import text_handler
from helpers.agents.session.session_store import (
    append_turn,
    get_history,
    session_exists,
    update_session_title,
)
from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger
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
                            "The James Webb Space Telescope was launched on 25 December 2021."
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
):
    """Send a message and receive a full response.

    The agent system will:
    1. Parse slash commands for deterministic routing
    2. Search personal memory and inject relevant facts
    3. Route to the appropriate specialist agent (or handle directly)
    4. Return the response with tool and agent metadata

    For token-by-token streaming, use `POST /chat/stream` instead.
    """
    logger.info(
        "POST /chat — session='%s' message=%r attachments=%d",
        session_id or "(none)",
        message[:80] if message else "",
        len(attachments),
    )

    window = load_config().get("orchestrator", {}).get("history_window", 20)

    exists = session_id and await session_exists(session_id)
    if exists:
        history = await get_history(session_id, max_turns=window)
    else:
        history = []
        if session_id:
            logger.warning("Unknown session_id '%s' — proceeding without history", session_id)

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

        file_url: str | None = None
        history_response = response_text
        m = re.search(r"[\w/\\.:+-]+\.(?:pdf|md)", response_text)
        if m:
            file_url = f"/files/{Path(m.group(0)).name}"
            response_text = "Your presentation is ready."
            history_response = "Presentation generated successfully."

        history_user = (
            handler_result.user_content
            if primary and handler_result.user_content
            else message
        )
        if session_id and exists:
            await append_turn(
                session_id,
                history_user,
                history_response,
                assistant_metadata={
                    "tools_used": tools_used,
                    "agents_trace": agents_trace,
                },
            )
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
