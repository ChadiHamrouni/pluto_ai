from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from helpers.core.config_loader import load_config
from helpers.core.db import init_db
from helpers.core.logger import get_logger
from routes.auth import router as auth_router
from routes.autonomous import router as autonomous_router
from routes.chat import router as chat_router
from routes.files import router as files_router
from routes.settings import router as settings_router

logger = get_logger(__name__)


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

    logger.info("Server ready on %s:%d", config["api"]["host"], config["api"]["port"])

    yield

    logger.info("Shutting down.")


def create_app() -> FastAPI:
    config = load_config()

    app = FastAPI(
        title="Personal AI Assistant",
        description=(
            "A local AI assistant powered by Ollama, OpenAI Agents SDK, "
            "FastAPI, and SQLite. Supports note-taking, slide generation, "
            "and persistent memory."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(autonomous_router)
    app.include_router(settings_router)
    app.include_router(files_router)

    @app.get("/", tags=["health"])
    async def root():
        return {"status": "ok", "service": "personal-ai-assistant", "version": "1.0.0"}

    @app.get("/health", tags=["health"])
    async def health():
        cfg = load_config()
        return {
            "status": "healthy",
            "orchestrator_model": cfg["orchestrator"]["model"],
            "ollama_base_url": cfg["ollama"]["base_url"],
            "db_path": cfg["memory"]["db_path"],
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
