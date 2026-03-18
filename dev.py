"""
Standalone dev REPL — runs the orchestrator without starting the API server.
Usage:  python dev.py
"""
from __future__ import annotations

import asyncio
import os
import time

# Disable SDK tracing (we're on Ollama, not OpenAI)
os.environ.setdefault("OPENAI_API_KEY", "no-tracing")
os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"

from rich.console import Console

from helpers.config_loader import load_config
from helpers.db import init_db
from agents.orchestrator import run_orchestrator

console = Console()


async def _setup() -> None:
    config = load_config()
    for key in ("notes_dir", "slides_dir"):
        os.makedirs(config["storage"][key], exist_ok=True)
    os.makedirs(config["memory"]["embeddings_path"], exist_ok=True)
    await init_db(config["memory"]["db_path"])


async def _repl() -> None:
    await _setup()
    history: list = []
    console.print("[bold green]Personal AI — dev REPL[/bold green]  (Ctrl-C or blank line to quit)\n")
    while True:
        try:
            msg = input("you> ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not msg:
            break
        t0 = time.perf_counter()
        response = await run_orchestrator(msg, history)
        elapsed = time.perf_counter() - t0
        console.print(f"\n[bold cyan]assistant>[/bold cyan] {response}")
        console.print(f"[dim]({elapsed:.2f}s)[/dim]\n")
        history.append({"role": "user", "content": msg})
        history.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    asyncio.run(_repl())
