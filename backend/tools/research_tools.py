"""Research tools for multi-step web browsing and synthesis."""

from __future__ import annotations

import re

import httpx
from agents import function_tool

from helpers.core.logger import get_logger

logger = get_logger(__name__)


@function_tool
async def fetch_page(url: str) -> str:
    """Fetch a web page and return its full text content (up to 5000 chars).

    Use this to read the full content of a specific URL found via web_search.
    Returns the page text with HTML stripped.

    Args:
        url: The full URL to fetch.
    """
    if not url:
        return "Error: no URL provided."
    try:
        headers = {"User-Agent": "Mozilla/5.0 (research bot)"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=15, follow_redirects=True)
            response.raise_for_status()
        text = re.sub(r"<script[^>]*>.*?</script>", "", response.text, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return "Page returned no text content."
        return text[:5000]
    except Exception as exc:
        logger.warning("fetch_page failed for %s: %s", url, exc)
        return f"Failed to fetch page: {exc}"


@function_tool
def take_research_note(note: str) -> str:
    """Save a research finding to your working notes for later synthesis.

    Use this to accumulate key facts, quotes, and data points as you
    research a topic. These notes will be available in your context
    for writing the final summary.

    Args:
        note: A concise research finding with its source.
    """
    # This tool doesn't persist — it just returns the note as confirmation,
    # which stays in the agent's conversation context for synthesis.
    logger.info("Research note taken: %s", note[:80])
    return f"Noted: {note}"
