from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, status

from helpers.agents.execution.ollama_client import get_ollama_base_url
from helpers.core.config_loader import load_config, reload_config
from helpers.core.logger import get_logger
from models.settings import AgentModels

logger = get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])

# Agent keys exposed in the UI — maps display label → config.json section key
_AGENT_KEYS = {
    "orchestrator": "orchestrator",
    "notes_agent": "notes_agent",
    "slides_agent": "slides_agent",
    "autonomous": "autonomous",
}


@router.get("/models")
async def list_models():
    """Return model names currently pulled in the user's local Ollama."""
    base_url = get_ollama_base_url()
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        return {"models": sorted(models)}
    except Exception as exc:
        logger.warning("Could not reach Ollama to list models: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Cannot reach Ollama at {base_url}: {exc}",
        )


@router.get("/agents")
async def get_agent_models():
    """Return the currently configured model for each agent."""
    cfg = load_config()
    return {key: cfg.get(key, {}).get("model", "") for key in _AGENT_KEYS}


@router.post("/agents")
async def set_agent_models(
    body: AgentModels,
):
    """Persist model choices per agent into config.json."""
    # Locate config.json — same resolution as config_loader
    config_path = os.environ.get("CONFIG_PATH", "")
    if not config_path:
        base_dir = Path(__file__).resolve().parent.parent
        config_path = str(base_dir / "config.json")

    if not Path(config_path).exists():
        raise HTTPException(status_code=404, detail=f"config.json not found at {config_path}")

    with open(config_path) as f:
        raw = json.load(f)

    updates = {
        "orchestrator": body.orchestrator,
        "notes_agent": body.notes_agent,
        "slides_agent": body.slides_agent,
        "autonomous": body.autonomous,
    }
    for key, model in updates.items():
        if model:
            raw.setdefault(key, {})["model"] = model

    with open(config_path, "w") as f:
        json.dump(raw, f, indent=2)

    reload_config()

    # Bust agent singletons so the next request picks up the new models
    from my_agents.notes_agent import reset_notes_agent
    from my_agents.orchestrator import reset_orchestrator
    from my_agents.slides_agent import reset_slides_agent

    reset_orchestrator()
    reset_notes_agent()
    reset_slides_agent()

    logger.info("Agent models updated: %s", updates)
    return {"status": "ok", "updated": updates}
