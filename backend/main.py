from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from helpers.core.config_loader import load_config
from helpers.core.db import init_db
from helpers.core.exceptions import PlutoError
from helpers.core.logger import get_logger, setup_logging
from routes.auth import router as auth_router
from routes.files import router as files_router
from routes.messaging import router as messaging_router
from routes.sessions import router as sessions_router
from routes.settings import router as settings_router
from routes.stream import router as stream_router
from routes.transcribe import router as transcribe_router

setup_logging()

logger = get_logger(__name__)


async def _pin_models_in_memory(base_url: str, models: list[str]) -> None:
    """Send keep_alive=-1 to Ollama's native API for each model so they stay
    resident in VRAM between requests. Fire-and-forget; failures are logged
    but never block startup."""
    import httpx

    async with httpx.AsyncClient(timeout=10) as client:
        for model in models:
            try:
                await client.post(
                    f"{base_url}/api/generate",
                    json={"model": model, "keep_alive": -1},
                )
                logger.info("Pinned model in memory: %s", model)
            except Exception as exc:
                logger.warning("Could not pin model %s: %s", model, exc)



@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting personal AI assistant...")

    config = load_config()

    # Ensure required data directories exist
    memory_dir = config.get("memory", {}).get("memory_dir", "data/memory")
    os.makedirs(memory_dir, exist_ok=True)
    for dir_key in ("notes_dir", "slides_dir"):
        path = config["storage"][dir_key]
        os.makedirs(path, exist_ok=True)

    # Initialise SQLite database
    await init_db(config["memory"]["db_path"])

    # Pin all models in Ollama VRAM so they never unload between requests.
    # Collects the distinct model names from every section that defines one.
    from helpers.agents.execution.ollama_client import get_ollama_base_url
    _models_to_pin = [config["orchestrator"]["model"]]
    asyncio.create_task(_pin_models_in_memory(get_ollama_base_url(), _models_to_pin))


    # TTS model — disabled while focusing on agent/tool testing
    # from helpers.tools.tts import load_model as load_tts
    # try:
    #     load_tts()
    # except Exception as e:
    #     logger.warning("TTS model failed to load (voice mode disabled): %s", e)

    # Pre-warm the STT model so the first transcription request is instant.
    try:
        from helpers.tools.stt import _get_model
        await asyncio.get_event_loop().run_in_executor(None, _get_model)
    except Exception as e:
        logger.warning("STT model failed to pre-load (transcription will load on first use): %s", e)

    logger.info("Server ready on %s:%d", config["api"]["host"], config["api"]["port"])

    yield

    logger.info("Shutting down.")


_TAGS_METADATA = [
    {
        "name": "chat",
        "description": (
            "Send messages and receive responses from the multi-agent system. "
            "Use `POST /chat` for standard JSON responses or `POST /chat/stream` for "
            "real-time Server-Sent Events (SSE) token streaming. "
            "Attach images, PDFs, or text files to any non-streaming request. "
            "Pass a `session_id` (from `POST /chat/session`) to maintain conversation history."
        ),
    },
    {
        "name": "health",
        "description": "Liveness and readiness probes.",
    },
    {
        "name": "files",
        "description": "Download generated files (slides PDFs, plot images).",
    },
    {
        "name": "settings",
        "description": "Read and update runtime configuration (models, hyperparameters).",
    },
]


limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])

# Paths exempt from CSRF check (auth endpoints, health, docs)
_CSRF_EXEMPT = {
    "/auth/login", "/auth/refresh", "/auth/verify",
    "/", "/health", "/docs", "/redoc", "/openapi.json",
}


class CSRFMiddleware(BaseHTTPMiddleware):
    """Require ``X-Requested-With`` header on state-changing requests.

    This forces browsers to issue a CORS preflight (since ``X-Requested-With``
    is not a CORS-safelisted header), which blocks cross-origin form POSTs.
    """

    async def dispatch(self, request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if request.url.path not in _CSRF_EXEMPT:
                if "x-requested-with" not in request.headers:
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Missing X-Requested-With header."},
                    )
        return await call_next(request)


def create_app() -> FastAPI:
    config = load_config()

    app = FastAPI(
        title="Pluto — Personal AI Assistant",
        description=(
            "A **local-first** multi-agent AI assistant. No cloud, no API keys — "
            "everything runs on your machine via Ollama.\n\n"
            "## Agents\n"
            "- **Orchestrator** — central router with memory injection and web search\n"
            "- **NotesAgent** — create and retrieve structured markdown notes\n"
            "- **SlidesAgent** — generate Marp PDF presentations\n"
            "- **ResearchAgent** — multi-step web research with citations\n"
            "- **CalendarAgent** — natural language scheduling\n\n"
            "## Routing\n"
            "Slash commands (`/note`, `/slides`, `/research`, `/calendar`) deterministically "
            "route to specialist agents. All other messages go through"
            " the Orchestrator's LLM routing.\n\n"
            "## Streaming\n"
            "Use `POST /chat/stream` to receive token-by-token SSE events including "
            "`tool_call` and `agent_handoff` visibility in real time."
        ),
        version="2.0.0",
        openapi_tags=_TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS: allow Tauri dev server + configurable origins
    allowed_origins = config.get("api", {}).get(
        "cors_origins",
        [
            "http://localhost:1420",  # Tauri dev
            "http://localhost:5173",  # Vite dev
            "http://localhost:8000",  # FastAPI (same-origin)
            "tauri://localhost",  # Tauri production
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "Authorization", "X-Requested-With"],
    )

    # Security headers
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    # CSRF protection — requires X-Requested-With on state-changing requests
    app.add_middleware(CSRFMiddleware)

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(auth_router)
    app.include_router(sessions_router)
    app.include_router(messaging_router)
    app.include_router(stream_router)
    app.include_router(settings_router)
    app.include_router(files_router)
    app.include_router(transcribe_router)

    @app.get("/", tags=["health"], summary="Root")
    async def root():
        """Liveness probe. Always returns 200 if the process is running."""
        return {"status": "ok", "service": "Pluto", "version": "2.0.0"}

    @app.get(
        "/health",
        tags=["health"],
        summary="Readiness probe",
        responses={
            200: {
                "description": "Service is healthy and ready.",
                "content": {
                    "application/json": {
                        "example": {
                            "status": "healthy",
                            "orchestrator_model": "qwen2.5:3b",
                            "ollama_base_url": "http://localhost:11434",
                            "db_path": "data/memory.db",
                        }
                    }
                },
            }
        },
    )
    async def health():
        """Readiness probe."""
        cfg = load_config()
        return {
            "status": "healthy",
            "orchestrator_model": cfg["orchestrator"]["model"],
        }

    # ── Structured error handlers ───────────────────────────────────────────

    @app.exception_handler(PlutoError)
    async def Pluto_error_handler(_request: Request, exc: PlutoError):
        status_map = {
            "model_unavailable": 503,
            "context_exceeded": 413,
            "tool_error": 502,
            "agent_error": 500,
        }
        return JSONResponse(
            status_code=status_map.get(exc.error_code, 500),
            content={"error": exc.error_code, "message": str(exc)},
        )

    return app


app = create_app()


if __name__ == "__main__":
    config = load_config()
    uvicorn.run(
        "main:app",
        host=config["api"]["host"],
        port=config["api"]["port"],
        reload=True,
        log_level="info",
    )
