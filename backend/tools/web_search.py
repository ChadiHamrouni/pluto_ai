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
        content = snippet
        if page_text and len(page_text) > len(snippet):
            content = f"{snippet}\n\n{page_text}"

        sections.append(f"[Result {i}] {title}\nSource: {url}\n{content}")
        source_lines.append(f"- [{title}]({url})")

    body = "\n\n---\n\n".join(sections)
    sources_block = "\n\nSources:\n" + "\n".join(source_lines)
    return body + sources_block


@function_tool
async def fetch_page(url: str) -> str:
    """Fetch a web page and return its plain-text content (up to 8000 chars).

    Use this to deep-read a specific URL found via web_search when you need
    more detail than the snippet provided.

    Args:
        url: The full URL to fetch.

    Returns:
        Extracted plain text from the page (up to 8000 chars), or an error message.
    """
    if not url:
        return "Error: no URL provided."
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=15, follow_redirects=True)
            response.raise_for_status()
        text = response.text
        for tag in ("script", "style", "nav", "header", "footer", "aside", "noscript"):
            text = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return "Page returned no text content."
        return text[:8000]
    except Exception as exc:
        logger.warning("fetch_page failed for %s: %s", url, exc)
        return f"Failed to fetch page: {exc}"


async def _fetch_text(url: str) -> str:
    """Fetch a URL and return the first 3000 chars of plain text (used internally by web_search)."""
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
