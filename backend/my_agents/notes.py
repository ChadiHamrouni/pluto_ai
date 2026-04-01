from __future__ import annotations

from agents import Agent, ModelSettings

from helpers.agents.execution.instructions_loader import load_instructions
from helpers.agents.execution.ollama_client import get_model
from helpers.core.config_loader import load_config
from tools.notes import create_note, get_note, list_notes

_notes_agent: Agent | None = None


def reset_notes_agent() -> None:
    global _notes_agent
    _notes_agent = None


def get_notes_agent() -> Agent:
    """
    Return the notes agent singleton, creating it on first call.

    The notes agent handles all note-taking operations: creating structured
    markdown notes, listing existing notes (optionally by category), and
    retrieving the full content of a specific note by title.
    """
    global _notes_agent
    if _notes_agent is not None:
        return _notes_agent

    notes_cfg = load_config()["notes_agent"]

    _notes_agent = Agent(
        name="NotesAgent",
        model=get_model(notes_cfg["model"]),
        instructions=load_instructions("agents/notes_agent"),
        tools=[create_note, list_notes, get_note],
        model_settings=ModelSettings(
            temperature=notes_cfg.get("temperature", 0.5),
            tool_choice=notes_cfg.get("tool_choice", "required"),
        ),
    )

    return _notes_agent
