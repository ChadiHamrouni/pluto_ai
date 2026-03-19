"""
Text embedder backed by Ollama's /api/embeddings endpoint.

Uses qwen3-embedding:0.6b (or whatever model is set in config.json
knowledge_base.embedding_model) running inside the Ollama container.

No model weights are loaded in the app process — Ollama owns the model.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Union

import httpx
import numpy as np

from helpers.core.config_loader import load_config
from helpers.core.logger import get_logger

logger = get_logger(__name__)

_ready: bool = False


def is_ready() -> bool:
    """Return True once we have confirmed Ollama embedding endpoint is reachable."""
    return _ready


def load_model() -> None:
    """
    Mark embedding as ready without probing Ollama at startup.

    We skip the warm-up probe so the embedding model is NOT loaded into VRAM
    at startup — the LLM (qwen3.5:2b) needs that VRAM. The embedding model
    will load on first actual use (RAG search), at which point Ollama will
    evict the LLM if needed (OLLAMA_MAX_LOADED_MODELS=1).
    """
    global _ready
    _ready = True
    logger.info("Embedding model ready (lazy — will load on first use via Ollama).")


def _call_ollama(base_url: str, model: str, text: str) -> List[float]:
    """POST to Ollama /api/embeddings and return the embedding vector."""
    url = base_url.rstrip("/") + "/api/embeddings"
    timeout = load_config()["ollama"].get("request_timeout_seconds", 30)

    response = httpx.post(
        url,
        json={"model": model, "prompt": text},
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    embedding = data.get("embedding")
    if not embedding:
        raise ValueError(f"Ollama returned no embedding. Response: {data}")

    return embedding


def _normalise(vec: List[float]) -> List[float]:
    arr = np.array(vec, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm > 0:
        arr = arr / norm
    return arr.tolist()


def embed_text(text: str) -> List[float]:
    """Embed a text string into a dense vector via Ollama."""
    global _ready
    config = load_config()
    model = config["knowledge_base"]["embedding_model"]
    base_url = config["ollama"]["base_url"]

    vec = _call_ollama(base_url, model, text)
    _ready = True  # mark ready on first successful call
    return _normalise(vec)


def embed(content: Union[str, Path]) -> List[float]:
    """
    Embed text content. Images are not supported with the text-only
    qwen3-embedding model — pass the text description or extracted text instead.
    """
    return embed_text(str(content))
