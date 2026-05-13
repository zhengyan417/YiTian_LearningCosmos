"""Tavily search tool for the deep research workflow.

Uses Tavily to discover relevant URLs, then fetches each page and converts it
to markdown so the LLM can read full article content rather than a snippet.
"""

import asyncio

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


async def _fetch_webpage_content(url: str) -> str:
    """Fetch a URL and convert the HTML body to markdown."""
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            timeout=settings.RESEARCH_WEBPAGE_FETCH_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            return markdownify(response.text)
    except Exception as e:
        logger.warning("webpage_fetch_failed", url=url, error=str(e))
        return f"Error fetching content from {url}: {str(e)}"


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
        )
    except Exception as e:
        logger.exception("tavily_search_failed", query=query, error=str(e))
        return f"Search failed for '{query}': {str(e)}"

    results = search_results.get("results", [])
    if not results:
        return f"No results found for '{query}'."

    contents = await asyncio.gather(*[_fetch_webpage_content(r["url"]) for r in results])

    formatted = []
    for result, content in zip(results, contents, strict=True):
        formatted.append(f"## {result.get('title', 'Untitled')}\n**URL:** {result['url']}\n\n{content}\n\n---\n")

    logger.info("tavily_search_completed", query=query, result_count=len(results))
    return f"Found {len(results)} result(s) for '{query}':\n\n" + "\n".join(formatted)
