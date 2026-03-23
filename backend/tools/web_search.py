from __future__ import annotations

import re

import httpx
from agents import function_tool
from ddgs import DDGS

from helpers.core.logger import get_logger

logger = get_logger(__name__)


@function_tool
async def web_search(query: str, max_results: int = 3) -> str:
    """Search the web and return extracted page content.

    Args:
        query: The search query — be specific, include location/date when relevant.
        max_results: Number of pages to fetch and extract (default 3).

    Returns:
        Concatenated page text from top results with a SOURCES block at the end.
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
        # Always keep the snippet — DDGS often extracts the direct answer
        # (e.g. current temperature, definition). Append page text if we got it.
        content = snippet
        if page_text and len(page_text) > len(snippet):
            content = f"{snippet}\n\n{page_text}"

        sections.append(f"[Result {i}] {title}\nSource: {url}\n{content}")
        source_lines.append(f"- [{title}]({url})")

    body = "\n\n---\n\n".join(sections)
    sources_block = "\n\nSources:\n" + "\n".join(source_lines)
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
        return text[:3000]
    except Exception:
        return ""
