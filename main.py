from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from helpers.config_loader import load_config
from helpers.db import init_db
from helpers.logger import get_logger
from routes.auth import router as auth_router
from routes.chat import router as chat_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.
    Runs startup logic before yielding and cleanup (if any) after.
    """
    logger.info("Starting personal AI assistant...")

    # Load configuration
    config = load_config()
    logger.info("Configuration loaded successfully.")

    # Ensure required data directories exist
    for dir_key in ("notes_dir", "slides_dir"):
        path = config["storage"][dir_key]
        os.makedirs(path, exist_ok=True)
        logger.info("Ensured directory exists: %s", path)

    embeddings_path = config["memory"]["embeddings_path"]
    os.makedirs(embeddings_path, exist_ok=True)
    logger.info("Ensured embeddings directory exists: %s", embeddings_path)

    # Initialise the SQLite database (creates tables if absent)
    db_path = config["memory"]["db_path"]
    await init_db(db_path)
    logger.info("Database ready at %s", db_path)

    logger.info(
        "Server ready. Listening on %s:%d",
        config["api"]["host"],
        config["api"]["port"],
    )

    yield  # application runs here

    logger.info("Shutting down personal AI assistant.")


def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    config = load_config()

    app = FastAPI(
        title="Personal AI Assistant",
        description=(
            "A local AI assistant powered by Ollama, OpenAI Agents SDK, "
            "FastAPI, and SQLite.  Supports note-taking, slide generation, "
            "and persistent memory with semantic search."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS — allow all origins for local development; tighten in production
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount routers
    app.include_router(auth_router)
    app.include_router(chat_router)

    @app.get("/", tags=["health"])
    async def root():
        """Health-check endpoint."""
        return {
            "status": "ok",
            "service": "personal-ai-assistant",
            "version": "1.0.0",
        }

    @app.get("/health", tags=["health"])
    async def health():
        """Detailed health check including config summary."""
        cfg = load_config()
        return {
            "status": "healthy",
            "orchestrator_model": cfg["orchestrator"]["model"],
            "ollama_base_url": cfg["orchestrator"]["base_url"],
            "db_path": cfg["memory"]["db_path"],
            "streaming_enabled": cfg["api"]["streaming"],
        }

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
