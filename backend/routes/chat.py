from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from handlers.file_handler import file_handler
from handlers.text_handler import text_handler
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
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".webp": "image/webp",
    ".gif": "image/gif",  ".bmp": "image/bmp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


@router.post("/session", tags=["chat"])
async def create_session(_user: dict = Depends(get_current_user)):
    """Create a new server-side conversation session."""
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


@router.post("", response_model=ChatResponse)
async def chat(
    message: str = Form(default=""),
    session_id: str = Form(default=""),
    attachments: List[UploadFile] = File(default=[]),
    _user: dict = Depends(get_current_user),
):
    """Send a message and get a response.

    Pass ``session_id`` (from POST /chat/session) to use server-side history.
    If omitted or unknown, the request is treated as a fresh stateless turn.

    Supported attachment types: images (jpg/png/webp/gif/bmp), PDF, .txt.
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
            attachment_meta.append(Attachment(
                filename=upload.filename,
                mime_type=_MIME_MAP.get(ext, "application/octet-stream"),
                size_bytes=len(data),
            ))

        primary = temp_paths[0] if temp_paths else None

        tools_used: list[str] = []
        agents_trace: list[str] = []
        if primary:
            extra_context = ""
            if len(temp_paths) > 1:
                names = ", ".join(a.filename for a in attachment_meta[1:])
                extra_context = f"\n\n[Additional attached files: {names}]"
            full_message = message + extra_context
            response_text, _, tools_used, agents_trace = await file_handler(full_message, history, primary)
        else:
            response_text, _, tools_used, agents_trace = await text_handler(message, history)

        logger.info("Response ready (%d chars) for session '%s'", len(response_text), session_id or "(none)")

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
