"""Tavily search tool for the deep research workflow.

Uses Tavily to discover relevant URLs and their pre-fetched page content
(``include_raw_content=True``). Falls back to a local httpx fetch when Tavily
returns no raw content for a hit, so the LLM gets full article content rather
than just a snippet whenever possible — and bot-protected pages that 403 our
local fetch usually still come through via Tavily.
"""

import asyncio
from typing import Any

import httpx
from langchain_core.tools import tool
from markdownify import markdownify
from tavily import TavilyClient

from app.core.config import settings
from app.core.logging import logger

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)

_tavily_client: TavilyClient | None = None


def _get_client() -> TavilyClient:
    """Lazily build the Tavily client so import doesn't fail when the key is absent."""
    global _tavily_client
    if _tavily_client is None:
        if not settings.TAVILY_API_KEY:
            raise RuntimeError("TAVILY_API_KEY is not configured")
        _tavily_client = TavilyClient(api_key=settings.TAVILY_API_KEY)
    return _tavily_client


def _apply_char_limit(text: str, url: str) -> str:
    """Cap page content at ``RESEARCH_WEBPAGE_MAX_CHARS``.

    A sub-agent concatenates every search result it accumulates, so without
    this cap a few large pages can blow past the LLM context window.
    """
    limit = settings.RESEARCH_WEBPAGE_MAX_CHARS
    if len(text) > limit:
        logger.info("webpage_content_truncated", url=url, original_chars=len(text), limit=limit)
        return text[:limit] + "\n\n[... content truncated]"
    return text


async def _fetch_webpage_content(url: str) -> str:
    """Fetch a URL via httpx and convert the HTML body to markdown.

    Used as a fallback when Tavily did not return ``raw_content`` for a hit.
    Many bot-protected sites (Cloudflare etc.) return 403 here — failures are
    swallowed into an error string so the agent can still produce an answer
    from whatever other results it has.
    """
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            timeout=settings.RESEARCH_WEBPAGE_FETCH_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            markdown = markdownify(response.text)
    except Exception as e:
        logger.warning("webpage_fetch_failed", url=url, error=str(e))
        return f"Error fetching content from {url}: {str(e)}"

    return _apply_char_limit(markdown, url)


async def _resolve_content(result: dict[str, Any]) -> str:
    """Prefer Tavily's pre-fetched ``raw_content``; fall back to a local httpx fetch.

    Tavily scrapes server-side with its own proxies and TLS fingerprints, so it
    bypasses most of the anti-bot 403s that block our own httpx requests. When
    Tavily returns no raw content for a hit (field missing or empty) we still
    try the local fetch as a best-effort second chance.
    """
    url = result["url"]
    raw = result.get("raw_content")
    if isinstance(raw, str) and raw.strip():
        logger.debug("webpage_content_from_tavily", url=url, chars=len(raw))
        return _apply_char_limit(raw, url)
    logger.debug("webpage_content_local_fallback", url=url)
    return await _fetch_webpage_content(url)


@tool(parse_docstring=True)
async def tavily_search(query: str) -> str:
    """Search the web for information on a given query.

    Uses Tavily to discover relevant URLs, then fetches and returns full webpage
    content as markdown so you can read the source material directly.

    Args:
        query: Search query to execute.

    Returns:
        Formatted search results with full webpage content for each hit.
    """
    try:
        client = _get_client()
        search_results = await asyncio.to_thread(
            client.search,
            query,
            max_results=settings.RESEARCH_TAVILY_MAX_RESULTS,
            topic="general",
            include_raw_content=True,
        )
    except Exception as e:
        logger.exception("tavily_search_failed", query=query, error=str(e))
        return f"Search failed for '{query}': {str(e)}"

    results = search_results.get("results", [])
    if not results:
        return f"No results found for '{query}'."

    contents = await asyncio.gather(*[_resolve_content(r) for r in results])

    formatted = []
    for result, content in zip(results, contents, strict=True):
        formatted.append(f"## {result.get('title', 'Untitled')}\n**URL:** {result['url']}\n\n{content}\n\n---\n")

    logger.info("tavily_search_completed", query=query, result_count=len(results))
    return f"Found {len(results)} result(s) for '{query}':\n\n" + "\n".join(formatted)
