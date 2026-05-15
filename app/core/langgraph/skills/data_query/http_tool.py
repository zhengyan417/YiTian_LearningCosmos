"""Whitelisted HTTP GET tool for the data_query skill.

This is the *only* path through which the LLM can hit an arbitrary internal API
(``web_research`` is for the public web). The host whitelist in
``settings.DATA_QUERY_ALLOWED_HOSTS`` is the only protection — there is no
network-level egress filter — so the list MUST be tight.
"""

import httpx
from langchain_core.tools import tool

from app.core.config import settings
from app.core.langgraph.skills.data_query.safety import check_url_host
from app.core.logging import logger


@tool(parse_docstring=True)
async def http_api_call(url: str) -> str:
    """Fetch JSON or text from a whitelisted internal HTTP API (GET only).

    HARD LIMITS:
    - Method is GET only — no POST / PUT / DELETE.
    - Host must be in DATA_QUERY_ALLOWED_HOSTS (operator-managed whitelist).
    - Response body is truncated at the configured byte limit.
    - For public-web pages use ``fetch_url`` (web_research skill) instead.

    Args:
        url: Absolute http(s) URL whose host is on the whitelist.

    Returns:
        ``HTTP <status>`` followed by a blank line then the body, or an error string on failure.
    """
    ok, reason = check_url_host(url)
    if not ok:
        return f"Error: {reason}"

    logger.info("data_query_http_invoked", url=url)
    try:
        async with httpx.AsyncClient(
            timeout=settings.DATA_QUERY_HTTP_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
            response = await client.get(url)
    except httpx.HTTPError as e:
        logger.warning("data_query_http_failed", url=url, error=str(e))
        return f"Error fetching {url}: {e}"

    body_bytes = response.content[: settings.DATA_QUERY_HTTP_MAX_RESPONSE_BYTES]
    truncated = len(response.content) > settings.DATA_QUERY_HTTP_MAX_RESPONSE_BYTES

    try:
        body = body_bytes.decode("utf-8")
    except UnicodeDecodeError:
        body = body_bytes.decode("utf-8", errors="replace")

    suffix = (
        f"\n\n[truncated: {len(response.content)} bytes total, showed first {len(body_bytes)}]" if truncated else ""
    )
    logger.info(
        "data_query_http_completed",
        url=url,
        status=response.status_code,
        body_chars=len(body),
        truncated=truncated,
    )
    return f"HTTP {response.status_code}\n\n{body}{suffix}"
