from __future__ import annotations

import asyncio

from agents import function_tool
from ddgs import DDGS

from helpers.core.logger import get_logger
from helpers.tools.web_search import (
    MAX_RESULTS,
    _query_cache,
    _url_cache,
    fetch_text_full,
    fetch_text_short,
    is_safe_url,
)

logger = get_logger(__name__)


@function_tool
async def web_search(query: str) -> str:
    """Search the web and return extracted page content from the top 3 results.

    Args:
        query: The search query — be specific, include location/date when relevant.

    Returns:
        Concatenated page text from top results with a SOURCES block at the end.
    """
    if query in _query_cache:
        logger.debug("web_search cache hit: %r", query)
        return _query_cache[query]

    try:
        results = DDGS().text(query, max_results=MAX_RESULTS)
    except Exception as exc:
        logger.error("DuckDuckGo search failed: %s", exc)
        return f"Search failed: {exc}"

    if not results:
        return "No results found for this query."

    # Fetch all pages concurrently instead of one-by-one
    urls = [r.get("href", "") for r in results]
    page_texts = await asyncio.gather(*[fetch_text_short(u) for u in urls])

    sections: list[str] = []
    source_lines: list[str] = []

    for i, (r, page_text) in enumerate(zip(results, page_texts), 1):
        title = r.get("title", "No title")
        url = r.get("href", "")
        snippet = r.get("body", "")

        # Prefer fetched page text over the snippet; use both if page adds value
        if page_text and len(page_text) > len(snippet):
            content = f"{snippet}\n\n{page_text}"
        else:
            content = snippet

        sections.append(f"[Result {i}] {title}\nSource: {url}\n{content}")
        source_lines.append(f"- [{title}]({url})")

    body = "\n\n---\n\n".join(sections)
    result = body + "\n\nSources:\n" + "\n".join(source_lines)
    _query_cache[query] = result
    return result


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

    if url in _url_cache:
        logger.debug("fetch_page cache hit: %s", url)
        return _url_cache[url]

    safe, reason = is_safe_url(url)
    if not safe:
        return f"Error: {reason}"

    text, error = await fetch_text_full(url)
    if error and not text:
        logger.warning("fetch_page failed for %s: %s", url, error)
        return f"Failed to fetch page: {error}"
    return text
