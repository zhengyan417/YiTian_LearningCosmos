"""Fetch an arbitrary URL and return its body as markdown.

Companion to ``tavily_search``: when the LLM already has a URL (e.g. from a
previous search result, a user-pasted link, or a citation it wants to verify),
this tool retrieves the page and converts the HTML to markdown so the model can
read the source directly.
"""

import httpx
from langchain_core.tools import tool
from markdownify import markdownify

from app.core.config import settings
from app.core.logging import logger

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)


@tool(parse_docstring=True)
async def fetch_url(url: str) -> str:
    """Fetch a webpage and return its body converted to markdown.

    Use this when you already have a URL (from a prior search hit, the user, or
    a citation) and need the full page content. For discovery when you only have
    a query, use ``tavily_search`` instead.

    Args:
        url: Absolute http(s) URL to fetch.

    Returns:
        Markdown rendering of the page body, or an error description on failure.
    """
    try:
        async with httpx.AsyncClient(
            headers={"User-Agent": _USER_AGENT},
            timeout=settings.RESEARCH_WEBPAGE_FETCH_TIMEOUT,
            follow_redirects=True,
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            content = markdownify(response.text)
            logger.info("fetch_url_completed", url=url, content_chars=len(content))
            return content
    except Exception as e:
        logger.warning("fetch_url_failed", url=url, error=str(e))
        return f"Error fetching {url}: {str(e)}"
