from __future__ import annotations

from agents import Agent, OpenAIChatCompletionsModel
from openai import AsyncOpenAI

from helpers.config_loader import load_config
from tools.slides_tools import generate_slides

_slides_agent: Agent | None = None


def get_slides_agent() -> Agent:
    """
    Return the slides agent singleton, creating it on first call.

    The slides agent converts the user's ideas or structured content into
    Marp-compatible markdown and generates a PDF presentation.
    """
    global _slides_agent
    if _slides_agent is not None:
        return _slides_agent

    config = load_config()
    slides_cfg = config["slides_agent"]
    orch_cfg = config["orchestrator"]

    client = AsyncOpenAI(
        base_url=orch_cfg["base_url"],
        api_key=orch_cfg["api_key"],
    )

    model = OpenAIChatCompletionsModel(
        model=slides_cfg["model"],
        openai_client=client,
    )

    _slides_agent = Agent(
        name="SlidesAgent",
        model=model,
        instructions=(
            "You are a presentation creation specialist. You help users turn their "
            "ideas, research notes, or outlines into polished slide decks using "
            "Marp markdown format.\n\n"
            "Marp slide conventions:\n"
            "- Separate slides with '---' on its own line.\n"
            "- Use '# Heading' for slide titles.\n"
            "- Use bullet points (- item) for concise content.\n"
            "- Keep each slide focused — no more than 5-6 bullet points per slide.\n"
            "- Start with a title slide, end with a summary or 'Thank You' slide.\n\n"
            "Available themes: default, gaia, uncover.\n\n"
            "Workflow:\n"
            "1. Understand the topic and desired structure from the user.\n"
            "2. Draft well-structured Marp markdown content.\n"
            "3. Call generate_slides_tool with the title, markdown, and chosen theme.\n"
            "4. Report the output file path to the user.\n\n"
            "If the user provides raw notes or bullet points, organise them into a "
            "logical presentation flow before generating."
        ),
        tools=[generate_slides],
    )

    return _slides_agent
