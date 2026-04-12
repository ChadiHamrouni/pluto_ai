"""
Web search helpers: SSRF protection, session caching, page fetching, and
the core search logic used by tools/web_search.py (@function_tool wrappers).
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from ddgs import DDGS

from helpers.core.logger import get_logger

logger = get_logger(__name__)

# ── Session-scoped deduplication caches ────────────────────────────────────
# Cleared at the start of each autonomous run.

_url_cache: dict[str, str] = {}    # url   → fetched text (up to 8000 chars)
_query_cache: dict[str, str] = {}  # query → full web_search result string


def clear_session_cache() -> None:
    """Clear URL and query caches. Call once at the start of each autonomous run."""
    _url_cache.clear()
    _query_cache.clear()
    logger.debug("Web search session cache cleared.")


# ── SSRF protection ─────────────────────────────────────────────────────────

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "0.0.0.0"}

_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_safe_url(url: str) -> tuple[bool, str]:
    """Validate that a URL does not point to a private/internal address.

    Returns (is_safe, reason).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Scheme '{parsed.scheme}' is not allowed — only http/https."

    hostname = parsed.hostname or ""
    if not hostname:
        return False, "No hostname in URL."

    if hostname in _BLOCKED_HOSTNAMES:
        return False, f"Hostname '{hostname}' is blocked."

    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in infos:
            ip = ipaddress.ip_address(sockaddr[0])
            for network in _PRIVATE_NETWORKS:
                if ip in network:
                    return False, f"Resolved IP {ip} is in a private range."
    except socket.gaierror:
        return False, f"Cannot resolve hostname '{hostname}'."

    return True, ""


# ── Page fetching ────────────────────────────────────────────────────────────

MAX_RESULTS = 6


def _strip_html(text: str, extra_tags: tuple[str, ...] = ()) -> str:
    """Remove HTML tags/entities and collapse whitespace."""
    for tag in ("script", "style", "nav", "header", "footer", "aside", "noscript") + extra_tags:
        text = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"&#?\w+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def fetch_text_short(url: str) -> str:
    """Fetch URL and return first 3 000 chars of plain text (used internally by web_search)."""
    if not url:
        return ""

    if url in _url_cache:
        cached = _url_cache[url]
        return cached[:3000] if cached else ""

    safe, _ = is_safe_url(url)
    if not safe:
        return ""

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (research bot)"},
                timeout=8,
                follow_redirects=True,
            )
            response.raise_for_status()
        text = _strip_html(response.text, extra_tags=("svg",))
        _url_cache[url] = text[:12000]
        return text[:3000]
    except Exception:
        return ""


async def fetch_text_full(url: str) -> tuple[str, str | None]:
    """Fetch URL and return up to 8000 chars of plain text.

    Returns (text, error_message). Caches both successes and failures.
    """
    if url in _url_cache:
        return _url_cache[url], None

    safe, reason = is_safe_url(url)
    if not safe:
        return "", reason

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
        text = _strip_html(response.text)
        if not text:
            return "", "Page returned no text content."
        result = text[:12000]
        _url_cache[url] = result
        return result, None
    except Exception as exc:
        error_msg = f"Failed to fetch page: {exc}"
        # Do NOT cache failures — retrying may succeed (transient network error)
        return "", error_msg


# ── High-level search + fetch helpers used by @function_tool wrappers ────────

async def cached_web_search(query: str) -> str:
    """
    Search the web for *query* and return extracted content from the top results.
    Results are cached for the lifetime of the process.
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

    urls = [r.get("href", "") for r in results]
    page_results = await asyncio.gather(*[fetch_text_full(u) for u in urls])

    sections: list[str] = []
    source_lines: list[str] = []

    for i, (r, (page_text, fetch_err)) in enumerate(zip(results, page_results), 1):
        title = r.get("title", "No title")
        url = r.get("href", "")
        snippet = r.get("body", "")
        if page_text and len(page_text) > len(snippet):
            content = f"{snippet}\n\n{page_text}"
        elif snippet:
            content = f"{snippet}\n\n[full page unavailable — snippet only]"
        else:
            content = "[no content retrieved]"
        sections.append(f"[Result {i}] {title}\nSource: {url}\n{content}")
        source_lines.append(f"- [{title}]({url})")

    result = "\n\n---\n\n".join(sections) + "\n\nSources:\n" + "\n".join(source_lines)
    _query_cache[query] = result
    return result


