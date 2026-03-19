from __future__ import annotations

import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from handlers.file_handler import file_handler
from handlers.text_handler import text_handler
from helpers.agents.session_store import (
    append_turn,
    get_history,
    new_session,
    session_exists,
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
    """Create a new server-side conversation session.

    Returns a session_id the client should include on every subsequent /chat
    request. The server keeps the rolling history — the client never needs to
    re-send past messages.
    """
    sid = new_session()
    logger.info("New session created: %s", sid)
    return {"session_id": sid}


@router.post("", response_model=ChatResponse)
async def chat(
    message: str = Form(default=""),
    session_id: str = Form(default=""),
    attachments: List[UploadFile] = File(default=[]),
    _user: dict = Depends(get_current_user),
):
    """Send a message and get a response.

    Pass ``session_id`` (from POST /chat/session) to use server-side history.
    If omitted or unknown, the request is treated as a fresh stateless turn
    (no history context).

    Supported attachment types: images (jpg/png/webp/gif/bmp), PDF, .txt.
    """
    logger.info(
        "POST /chat — session='%s' message=%r attachments=%d",
        session_id or "(none)",
        message[:80] if message else "",
        len(attachments),
    )

    # Resolve history from server-side session — no history in request body
    from helpers.core.config_loader import load_config
    window = load_config().get("orchestrator", {}).get("history_window", 20)

    if session_id and session_exists(session_id):
        history = get_history(session_id, max_turns=window)
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

        if primary:
            extra_context = ""
            if len(temp_paths) > 1:
                names = ", ".join(a.filename for a in attachment_meta[1:])
                extra_context = f"\n\n[Additional attached files: {names}]"
            full_message = message + extra_context
            response_text = await file_handler(full_message, history, primary)
        else:
            response_text = await text_handler(message, history)

        if isinstance(response_text, tuple):
            response_text = response_text[0]

        logger.info("Response ready (%d chars) for session '%s'", len(response_text), session_id or "(none)")

        # Persist this exchange into the session
        if session_id and session_exists(session_id):
            append_turn(session_id, message, response_text)

        return ChatResponse(response=response_text, attachments=attachment_meta)

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
