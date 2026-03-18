from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from my_agents.orchestrator import run_orchestrator
from helpers.routes.dependencies import get_current_user
from helpers.core.logger import get_logger
from models.chat import ChatMessage, ChatResponse

logger = get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    message: str = Form(...),
    history: str = Form(default="[]"),
    image: UploadFile | None = File(default=None),
    _user: dict = Depends(get_current_user),
):
    """Send a message (and optional image) to the AI assistant."""
    try:
        parsed_history = [ChatMessage(**m) for m in json.loads(history)]
    except Exception:
        parsed_history = []

    image_path: Path | None = None

    if image and image.filename:
        suffix = Path(image.filename).suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await image.read())
            image_path = Path(tmp.name)

    try:
        response_text = await run_orchestrator(
            message=message,
            history=parsed_history,
            image_path=image_path,
        )
    except Exception as exc:
        logger.error("Chat endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=f"Orchestrator error: {exc}")
    finally:
        if image_path and image_path.exists():
            image_path.unlink(missing_ok=True)

    return ChatResponse(response=response_text, has_image=image_path is not None)