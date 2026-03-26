from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import httpx
from agents import function_tool
from ddgs import DDGS

from helpers.core.logger import get_logger

logger = get_logger(__name__)


# ── SSRF protection ────────────────────────────────────────────────────────

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


def _is_safe_url(url: str) -> tuple[bool, str]:
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

    # Resolve hostname to IP and check against private ranges
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
            trimmed = page_text[:400]
            content = f"{snippet}\n\n{trimmed}"

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
    safe, reason = _is_safe_url(url)
    if not safe:
        return f"Error: {reason}"
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=15, follow_redirects=False)
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
    safe, _ = _is_safe_url(url)
    if not safe:
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (research bot)"}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=8, follow_redirects=False)
            response.raise_for_status()
        text = response.text
        # Strip noisy elements that confuse small models
        for tag in ("script", "style", "nav", "header", "footer", "aside", "noscript", "svg"):
            text = re.sub(rf"<{tag}[^>]*>.*?</{tag}>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Strip all remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Strip HTML entities
        text = re.sub(r"&[a-zA-Z]+;", " ", text)
        text = re.sub(r"&#?\w+;", " ", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:800]
    except Exception:
        return ""
