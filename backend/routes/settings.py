from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from helpers.agents.execution.ollama_client import get_ollama_base_url
from helpers.core.config_loader import load_config, reload_config
from helpers.core.logger import get_logger
from helpers.routes.dependencies import get_current_user
from models.settings import AgentModels

logger = get_logger(__name__)
router = APIRouter(prefix="/settings", tags=["settings"])


# ---------------------------------------------------------------------------
# Vault path
# ---------------------------------------------------------------------------

@router.get("/vault")
async def get_vault_path(_user: str = Depends(get_current_user)):
    """Return the currently configured Obsidian vault path."""
    cfg = load_config()
    return {"vault_path": cfg.get("obsidian", {}).get("vault_path", "")}


@router.put("/vault")
async def set_vault_path(body: dict, _user: str = Depends(get_current_user)):
    """Update the Obsidian vault path in config.json."""
    vault_path = body.get("vault_path", "")
    if not vault_path:
        raise HTTPException(status_code=400, detail="vault_path is required.")

    config_path = os.environ.get("CONFIG_PATH", "")
    if not config_path:
        base_dir = Path(__file__).resolve().parent.parent
        config_path = str(base_dir / "config.json")

    if not Path(config_path).exists():
        raise HTTPException(status_code=404, detail="config.json not found.")

    with open(config_path) as f:
        raw = json.load(f)

    raw.setdefault("obsidian", {})["vault_path"] = vault_path

    with open(config_path, "w") as f:
        json.dump(raw, f, indent=2)

    reload_config()
    logger.info("Vault path updated: %s", vault_path)
    return {"status": "ok", "vault_path": vault_path}

# Agent keys exposed in the UI — maps display label → config.json section key
_AGENT_KEYS = {
    "orchestrator": "orchestrator",
    "compactor": "compactor",
}


@router.get("/models")
async def list_models(_user: str = Depends(get_current_user)):
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
            detail="Cannot reach Ollama. Ensure the service is running.",
        )


@router.get("/agents")
async def get_agent_models(_user: str = Depends(get_current_user)):
    """Return the currently configured model for each agent."""
    cfg = load_config()
    return {key: cfg.get(key, {}).get("model", "") for key in _AGENT_KEYS}


@router.post("/agents")
async def set_agent_models(
    body: AgentModels,
    _user: str = Depends(get_current_user),
):
    """Persist model choices per agent into config.json."""
    # Validate model names against available Ollama models
    base_url = get_ollama_base_url()
    available: set[str] = set()
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        available = {m["name"] for m in r.json().get("models", [])}
    except Exception:
        logger.warning("Could not reach Ollama to validate model names")

    updates = {
        "orchestrator": body.orchestrator,
        "compactor": body.compactor,
    }
    if available:
        for key, model in updates.items():
            if model and model not in available:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Model '{model}' for '{key}' is not available in Ollama.",
                )

    # Locate config.json — same resolution as config_loader
    config_path = os.environ.get("CONFIG_PATH", "")
    if not config_path:
        base_dir = Path(__file__).resolve().parent.parent
        config_path = str(base_dir / "config.json")

    if not Path(config_path).exists():
        raise HTTPException(status_code=404, detail="config.json not found.")

    with open(config_path) as f:
        raw = json.load(f)

    for key, model in updates.items():
        if model:
            raw.setdefault(key, {})["model"] = model

    with open(config_path, "w") as f:
        json.dump(raw, f, indent=2)

    reload_config()

    # Bust the single-agent singleton so the next request picks up the new model
    from agent.single import reset_single_agent

    reset_single_agent()

    logger.info("Agent models updated: %s", updates)
    return {"status": "ok", "updated": updates}
