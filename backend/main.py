from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from helpers.core.config_loader import load_config
from helpers.core.db import init_db
from helpers.core.exceptions import JarvisError
from helpers.core.logger import get_logger, setup_logging
from helpers.cron.ingestion_job import run_ingestion
from routes.auth import router as auth_router
from routes.autonomous import router as autonomous_router
from routes.files import router as files_router
from routes.messaging import router as messaging_router
from routes.sessions import router as sessions_router
from routes.settings import router as settings_router
from routes.stream import router as stream_router
from routes.voice import router as voice_router

setup_logging()

logger = get_logger(__name__)


def _parse_cron_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' string into (hour, minute) integers. Defaults to 03:00 on error."""
    try:
        h, m = time_str.strip().split(":")
        return int(h), int(m)
    except Exception:
        return 3, 0


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

    for path in (
        config["knowledge_base"]["embeddings_path"],
        config["knowledge_base"]["files_path"],
    ):
        os.makedirs(path, exist_ok=True)

    # Initialise SQLite database
    await init_db(config["memory"]["db_path"])

    # Ensure ChromaDB data directory exists
    os.makedirs(config["knowledge_base"].get("chroma_path", "data/chroma"), exist_ok=True)

    # Schedule nightly knowledge base ingestion
    ingestion_hour, ingestion_minute = _parse_cron_time(
        config["knowledge_base"].get("ingestion_cron", "03:00")
    )
    scheduler = AsyncIOScheduler()
    scheduler.add_job(run_ingestion, "cron", hour=ingestion_hour, minute=ingestion_minute)
    scheduler.start()
    logger.info("Ingestion job scheduled at %02d:%02d", ingestion_hour, ingestion_minute)

    # Embedding model — disabled while focusing on agent/tool testing
    # from helpers.tools.embedder import load_model as load_embedder
    # load_embedder()

    # TTS model — disabled while focusing on agent/tool testing
    # from helpers.tools.tts import load_model as load_tts
    # try:
    #     load_tts()
    # except Exception as e:
    #     logger.warning("TTS model failed to load (voice mode disabled): %s", e)

    logger.info("Server ready on %s:%d", config["api"]["host"], config["api"]["port"])

    yield

    scheduler.shutdown(wait=False)
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
    {
        "name": "voice",
        "description": "Voice mode — VAD-triggered audio input and TTS audio output.",
    },
    {
        "name": "autonomous",
        "description": "Long-running autonomous task loops with plan-execute-reflect cycles.",
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
        title="Jarvis — Personal AI Assistant",
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
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
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
    app.include_router(autonomous_router)
    app.include_router(settings_router)
    app.include_router(files_router)
    app.include_router(voice_router)

    @app.get("/", tags=["health"], summary="Root")
    async def root():
        """Liveness probe. Always returns 200 if the process is running."""
        return {"status": "ok", "service": "jarvis", "version": "2.0.0"}

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

    @app.exception_handler(JarvisError)
    async def jarvis_error_handler(_request: Request, exc: JarvisError):
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
