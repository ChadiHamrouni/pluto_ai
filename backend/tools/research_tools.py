"""Research tools for multi-step web browsing and synthesis."""

from __future__ import annotations

import re

import httpx
from agents import function_tool

from helpers.core.logger import get_logger

logger = get_logger(__name__)


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
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=15, follow_redirects=True)
            response.raise_for_status()
        text = response.text
        # Remove non-content blocks first
        for tag in ("script", "style", "nav", "header", "footer", "aside", "noscript"):
            text = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Strip remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return "Page returned no text content."
        return text[:8000]
    except Exception as exc:
        logger.warning("fetch_page failed for %s: %s", url, exc)
        return f"Failed to fetch page: {exc}"


