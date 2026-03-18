"""Centralised Ollama HTTP client with TLS and JWT auth for remote Ollama."""

from __future__ import annotations

import httpx
from agents import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from helpers.core.config_loader import load_config


def _ollama_cfg() -> dict:
    config = load_config()
    return config.get("ollama", {})


def get_ollama_base_url() -> str:
    cfg = _ollama_cfg()
    return cfg.get("base_url", "http://localhost:11434").rstrip("/")


def _get_service_token() -> str:
    """
    Get the token used for backend-to-Ollama communication.

    This is the service_token from the ollama config — a long-lived secret
    shared between this backend and the reverse proxy in front of Ollama.
    Separate from user-facing JWTs.
    """
    cfg = _ollama_cfg()
    return cfg.get("service_token", "")


def _build_headers() -> dict[str, str]:
    """Build auth headers for Ollama requests."""
    token = _get_service_token()
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def get_httpx_client(timeout: float = 30) -> httpx.Client:
    """
    Build an httpx.Client pre-configured for the Ollama server.

    - Adds service bearer token if set
    - Respects verify_ssl (set to false only for self-signed certs in dev)
    """
    cfg = _ollama_cfg()
    verify = cfg.get("verify_ssl", True)

    return httpx.Client(
        base_url=get_ollama_base_url(),
        headers=_build_headers(),
        verify=verify,
        timeout=timeout,
    )


def get_model(model_name: str) -> OpenAIChatCompletionsModel:
    """Return an OpenAIChatCompletionsModel backed by the configured Ollama instance."""
    return OpenAIChatCompletionsModel(
        model=model_name,
        openai_client=get_openai_client(),
    )


def get_openai_client() -> AsyncOpenAI:
    """
    Build an AsyncOpenAI client pointed at Ollama's OpenAI-compatible
    endpoint, with service auth headers forwarded.
    """
    base_url = f"{get_ollama_base_url()}/v1"
    token = _get_service_token() or "ollama"

    return AsyncOpenAI(
        base_url=base_url,
        api_key=token,
        default_headers=_build_headers(),
    )
