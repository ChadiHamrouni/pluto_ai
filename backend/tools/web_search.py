from __future__ import annotations

from agents import function_tool

from helpers.core.logger import get_logger
from helpers.tools.web_search import cached_web_search

logger = get_logger(__name__)


@function_tool
async def web_search(query: str) -> str:
    """Search the web and return extracted page content from the top 3 results.

    Args:
        query: The search query — be specific, include location/date when relevant.

    Returns:
        Concatenated page text from top results with a SOURCES block at the end.
    """
    return await cached_web_search(query)
