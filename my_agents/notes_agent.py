from __future__ import annotations

from agents import Agent, OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from helpers.config_loader import load_config
from tools.notes_tools import create_note, get_note, list_notes

_notes_agent: Agent | None = None


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

    config = load_config()
    notes_cfg = config["notes_agent"]
    orch_cfg = config["orchestrator"]

    client = AsyncOpenAI(
        base_url=orch_cfg["base_url"],
        api_key=orch_cfg["api_key"],
    )

    model = OpenAIChatCompletionsModel(
        model=notes_cfg["model"],
        openai_client=client,
    )

    _notes_agent = Agent(
        name="NotesAgent",
        model=model,
        instructions=(
            "You are a note-taking assistant. Record exactly what the user says — nothing more.\n\n"
            "STRICT RULES:\n"
            "- NEVER invent, infer, or add content the user did not explicitly state.\n"
            "- NEVER expand with tips, suggestions, examples, or filler content.\n"
            "- Note content must be a faithful, verbatim-close record of the user's words.\n"
            "- If the message is too vague to create a meaningful note, ask ONE "
            "  clarifying question — do not guess or pad.\n\n"
            "Metadata rules:\n"
            "- Title: short, derived from the user's actual words.\n"
            "- Category: one of teaching, research, career, personal, ideas.\n"
            "- Tags: only words/concepts the user actually mentioned.\n\n"
            "When listing or retrieving notes, present them cleanly without added commentary."
        ),
        tools=[create_note, list_notes, get_note],
    )

    return _notes_agent
