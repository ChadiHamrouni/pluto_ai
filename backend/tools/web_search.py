from __future__ import annotations

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.web_search import cached_web_search

logger = get_logger(__name__)


@function_tool
async def web_search(query: str) -> str:
    """Search the web and return extracted full-page content from the top 6 results.

    Use this tool for any question whose answer may have changed since your training
    cutoff, or when the user explicitly asks to search the web.

    Query writing rules — follow these to get deep, useful results:
    - Use noun phrases, not questions. BAD: "what is the best Python ORM?"
      GOOD: "Python ORM comparison SQLAlchemy Django 2024"
    - Include the year when recency matters: "Tunisia inflation rate 2025"
    - Include domain context for technical topics: "FastAPI background tasks Starlette internals"
    - For a place or business: include city/country: "Café de Paris Sidi Bou Said Tunisia open"
    - For research mode: issue multiple calls with DIFFERENT angles per round:
        Round 1 — definition/overview: "retrieval augmented generation overview"
        Round 2 — tradeoffs/criticism: "retrieval augmented generation limitations hallucination"
        Round 3 — practical examples: "retrieval augmented generation production deployment 2024"
    - Never repeat the same query twice. If results are shallow, rephrase with a
      narrower angle or a different keyword combination.

    Returns:
        Up to 6 results. Each result contains the page title, source URL, DDG snippet,
        and up to 8 000 chars of extracted page text. Results marked
        "[full page unavailable — snippet only]" had fetch errors — consider retrying
        with a rephrased query or a different angle if those results were critical.
    """
    return await cached_web_search(query)
