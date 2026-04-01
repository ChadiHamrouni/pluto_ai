"""
Diagram metadata sidecar helpers.

When a diagram PNG is generated, a small JSON sidecar is written alongside it
so diagrams are searchable by title and mermaid source without needing
embeddings (images can't be semantically embedded with a text model).

Sidecar location: data/diagrams_meta/<filename>.png.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)


def _meta_dir() -> Path:
    cfg = load_config()
    diagrams_dir = cfg.get("storage", {}).get("diagrams_dir", "data/diagrams")
    d = Path(diagrams_dir).parent / "diagrams_meta"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_diagram_meta(filename: str, title: str, mermaid_source: str = "") -> None:
    """Write a JSON sidecar for a generated diagram PNG."""
    meta = {
        "filename": filename,
        "title": title,
        "mermaid_source": mermaid_source,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    sidecar = _meta_dir() / f"{filename}.json"
    try:
        sidecar.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Failed to write diagram sidecar for %s: %s", filename, exc)


def list_diagram_meta() -> list[dict]:
    """Return all diagram sidecar records."""
    results = []
    for p in _meta_dir().glob("*.json"):
        try:
            results.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results


def search_diagram_meta(query: str, top_k: int = 5) -> list[dict]:
    """
    Search diagram sidecars by substring match on title and mermaid source.
    Case-insensitive. Returns up to top_k results.
    """
    q = query.lower().strip()
    if not q:
        return []
    hits = [
        m for m in list_diagram_meta()
        if q in m.get("title", "").lower()
        or q in m.get("mermaid_source", "").lower()
    ]
    return hits[:top_k]
