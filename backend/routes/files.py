from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from helpers.core.config_loader import load_config
from helpers.routes.dependencies import get_current_user

router = APIRouter(prefix="/files", tags=["files"])


# Allowed base directories — only serve files from here
def _allowed_dirs() -> list[Path]:
    cfg = load_config()
    dirs = [
        Path(cfg["storage"]["slides_dir"]).resolve(),
        Path(cfg["storage"]["notes_dir"]).resolve(),
        Path(cfg["knowledge_base"]["files_path"]).resolve(),  # user-uploaded files
    ]
    diagrams_dir = cfg.get("storage", {}).get("diagrams_dir")
    if diagrams_dir:
        dirs.append(Path(diagrams_dir).resolve())
    return dirs


def _media_type(filename: str) -> str:
    if filename.endswith(".pdf"):
        return "application/pdf"
    if filename.endswith(".png"):
        return "image/png"
    if filename.endswith(".jpg") or filename.endswith(".jpeg"):
        return "image/jpeg"
    return "text/markdown"


@router.get("/{filename}")
async def serve_file(filename: str, _user: str = Depends(get_current_user)):
    """Serve a generated file (PDF, PNG, markdown) by filename."""
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    for base in _allowed_dirs():
        candidate = (base / filename).resolve()
        if candidate.parent == base and candidate.exists():
            return FileResponse(
                path=str(candidate),
                media_type=_media_type(filename),
                filename=filename,
            )

    raise HTTPException(status_code=404, detail=f"File '{filename}' not found")
