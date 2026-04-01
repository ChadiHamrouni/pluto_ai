"""Chat messaging endpoint: POST /chat (non-streaming, supports file attachments)."""

from __future__ import annotations

import re
import tempfile
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

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
from helpers.routes.dependencies import get_current_user
from models.chat import Attachment, ChatResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".pdf", ".txt"}
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
_MAX_MESSAGE_CHARS = 50_000


def _validate_session_id(session_id: str) -> None:
    """Raise 400 if session_id is non-empty but not a valid UUID."""
    if session_id:
        try:
            uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="session_id must be a valid UUID.",
            )

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

# Magic byte signatures for content-type validation
_MAGIC_BYTES: dict[str, list[bytes]] = {
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".bmp": [b"BM"],
    ".pdf": [b"%PDF"],
    ".webp": [b"RIFF"],  # RIFF header (WebP is RIFF-based)
}


def _validate_magic_bytes(data: bytes, ext: str) -> bool:
    """Return True if the file's magic bytes match the expected format."""
    signatures = _MAGIC_BYTES.get(ext)
    if signatures is None:
        return True  # No signature check for .txt etc.
    return any(data.startswith(sig) for sig in signatures)


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
    _user: str = Depends(get_current_user),
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
    if message and len(message) > _MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Message exceeds the {_MAX_MESSAGE_CHARS} character limit.",
        )
    _validate_session_id(session_id)

    logger.info(
        "POST /chat — session='%s' message=%r attachments=%d",
        session_id or "(none)",
        message[:40] if message else "",
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
            data = await upload.read(_MAX_UPLOAD_BYTES + 1)
            if len(data) > _MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File '{upload.filename}' exceeds the 50 MB limit.",
                )
            if not _validate_magic_bytes(data, ext):
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=(
                        f"File '{upload.filename}' content does not match"
                        f" its extension '{ext}'."
                    ),
                )
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
        m = re.search(r"[\w/\\.:+-]+\.(?:pdf|md|png)", response_text)
        if m:
            matched_name = Path(m.group(0)).name
            file_url = f"/files/{matched_name}"
            if matched_name.endswith(".png"):
                response_text = "Your diagram is ready."
                history_response = "Diagram generated successfully."
            else:
                response_text = "Your presentation is ready."
                history_response = "Presentation generated successfully."

        history_user = (
            handler_result.user_content
            if primary and handler_result.user_content
            else message
        )
        if session_id and exists:
            user_meta: dict = {}
            if attachment_meta:
                user_meta["attachment_names"] = [a.filename for a in attachment_meta]
            # Store the original display message so the bubble shows clean text,
            # not the full extracted PDF/OCR dump that lives in history_user.
            if primary and message:
                user_meta["display_content"] = message
            await append_turn(
                session_id,
                history_user,
                history_response,
                assistant_metadata={
                    "tools_used": tools_used,
                    "agents_trace": agents_trace,
                    **({"file_url": file_url} if file_url else {}),
                },
                user_metadata=user_meta or None,
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
    except Exception:
        logger.exception("Chat endpoint unhandled error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error.",
        )
    finally:
        for p in temp_paths:
            p.unlink(missing_ok=True)
