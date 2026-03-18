from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from handlers.text_handler import text_handler
from handlers.file_handler import file_handler
from helpers.routes.dependencies import get_current_user
from helpers.core.logger import get_logger
from models.chat import ChatMessage, ChatResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_FILE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".pdf"}

@router.post("", response_model=ChatResponse)
async def chat(
    message: str = Form(default=""),
    history: str = Form(default="[]"),
    image: UploadFile | None = File(default=None),
    _user: dict = Depends(get_current_user),
):
    """Dispatch to text, file, or voice handler based on payload."""
    t_start = time.perf_counter()
    handler_name = "UNKNOWN"
    handler_time = 0.0

    try:
        parsed_history = [ChatMessage(**m) for m in json.loads(history)]
    except Exception:
        parsed_history = []

    file_path: Path | None = None

    try:
        # Write uploaded file to a temp path if present
        if image and image.filename:
            suffix = Path(image.filename).suffix.lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(await image.read())
                file_path = Path(tmp.name)

        # ── Dispatch ────────────────────────────────────────────────────────
        if file_path and file_path.suffix.lower() in _FILE_EXTS:
            response_text = await file_handler(message, parsed_history, file_path)

        else:
            response_text = await text_handler(message, parsed_history, file_path)

        return ChatResponse(response=response_text, has_image=file_path is not None)

    except NotImplementedError as exc:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))
    except Exception as exc:
        logger.exception("Chat endpoint unhandled error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    finally:
        if file_path and file_path.exists():
            file_path.unlink(missing_ok=True)
