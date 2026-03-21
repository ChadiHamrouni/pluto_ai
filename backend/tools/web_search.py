from __future__ import annotations

import re

import httpx
from agents import function_tool
from ddgs import DDGS

from helpers.core.logger import get_logger

logger = get_logger(__name__)


@function_tool
async def web_search(query: str, max_results: int = 3) -> str:
    """Search the web for up-to-date information and return extracted page content.

    Searches DuckDuckGo for the query, fetches the top pages, and returns
    their extracted text concatenated together. Use this for any question
    that requires current information, definitions, or explanations you
    don't have in your training data.

    Args:
        query: The search query.
        max_results: Number of pages to fetch and extract (default 3).
    """
    try:
        results = DDGS().text(query, max_results=max_results)
    except Exception as exc:
        logger.error("DuckDuckGo search failed: %s", exc)
        return f"Search failed: {exc}"

    if not results:
        return "No results found for this query."

    sections: list[str] = []
    source_lines: list[str] = []

    for i, r in enumerate(results, 1):
        title = r.get("title", "No title")
        url = r.get("href", "")
        snippet = r.get("body", "")

        page_text = await _fetch_text(url)
        content = page_text if page_text else snippet

        sections.append(f"[Result {i}] {title}\nSource: {url}\n{content}")
        source_lines.append(f"- [{title}]({url})")

    body = "\n\n---\n\n".join(sections)
    sources_block = "\n\nSOURCES (include ALL of these verbatim in your response):\n" + "\n".join(
        source_lines
    )
    return body + sources_block


async def _fetch_text(url: str) -> str:
    """Fetch a URL asynchronously and return the first 1000 characters of plain text."""
    if not url:
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (research bot)"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=8, follow_redirects=True)
            response.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", response.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:1000]
    except Exception:
        return ""
