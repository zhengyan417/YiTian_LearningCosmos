"""Read-only SQL tool for the data_query skill.

A module-level ``AsyncConnectionPool`` (from psycopg3) is built lazily against
``settings.DATA_QUERY_READONLY_DSN`` so we only pay the connection cost when
the LLM actually invokes the tool. The pool is opened during the FastAPI
lifespan via ``warm_up`` and closed via ``shutdown``.
"""

import asyncio
from typing import (
    Any,
    List,
    Optional,
)

from langchain_core.tools import tool
from psycopg import AsyncConnection
from psycopg.rows import (
    DictRow,
    dict_row,
)
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.core.langgraph.skills.data_query.safety import check_sql_readonly
from app.core.logging import logger

_SqlPool = AsyncConnectionPool[AsyncConnection[DictRow]]
_pool: Optional[_SqlPool] = None


def _build_pool() -> _SqlPool:
    """Construct (but do not open) the async pool from the configured DSN."""
    return AsyncConnectionPool(
        settings.DATA_QUERY_READONLY_DSN,
        open=False,
        max_size=5,
        kwargs={
            "autocommit": True,
            "connect_timeout": 5,
            "row_factory": dict_row,
        },
    )


async def warm_up() -> None:
    """Open the read-only SQL pool so the first tool invocation isn't a cold start."""
    global _pool
    if not settings.DATA_QUERY_READONLY_DSN:
        return
    if _pool is None:
        _pool = _build_pool()
    if _pool.closed:
        return
    await _pool.open()
    logger.info("data_query_sql_pool_opened", max_size=5)


async def shutdown() -> None:
    """Close the read-only SQL pool on application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        logger.info("data_query_sql_pool_closed")
    _pool = None


def _format_rows(rows: List[Any]) -> str:
    """Render result rows as a markdown table, falling back to a notice when empty."""
    if not rows:
        return "_(query returned 0 rows)_"

    columns = list(rows[0].keys())
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body_lines = []
    for row in rows:
        body_lines.append("| " + " | ".join(_cell(row[col]) for col in columns) + " |")
    return "\n".join([header, separator, *body_lines])


def _cell(value: Any) -> str:
    """Render a single cell, escaping pipes and truncating long values."""
    text = "" if value is None else str(value)
    text = text.replace("|", "\\|").replace("\n", " ")
    if len(text) > 200:
        text = text[:200] + "…"
    return text


@tool(parse_docstring=True)
async def run_sql(query: str) -> str:
    """Execute a read-only SQL query against the configured analytics database.

    HARD LIMITS:
    - Only SELECT / WITH / EXPLAIN / SHOW are accepted; multi-statement input is rejected.
    - The configured DSN MUST point at a read-only DB account; this tool will not
      and cannot perform writes regardless of what you supply.
    - Result is truncated at the configured max-rows limit.

    Args:
        query: A single read-only SQL statement, no trailing semicolon required.

    Returns:
        A markdown table of results (or a "0 rows" notice), or an error string
        when validation / execution fails.
    """
    ok, reason = check_sql_readonly(query)
    if not ok:
        return f"Error: {reason}"

    if _pool is None or _pool.closed:
        return "Error: data_query SQL pool is not open. DATA_QUERY_READONLY_DSN is unset or the pool failed to start."

    truncated_for_log = query.strip().replace("\n", " ")[:200]
    logger.info("data_query_run_sql_invoked", sql=truncated_for_log)

    try:
        async with _pool.connection() as conn:
            async with conn.cursor() as cur:
                # psycopg accepts plain str at runtime; the stub demands LiteralString
                # to discourage SQL injection. We've already gated this through
                # check_sql_readonly, so the assertion here is intentional.
                await asyncio.wait_for(
                    cur.execute(query),  # pyright: ignore[reportCallIssue, reportArgumentType]
                    timeout=settings.DATA_QUERY_SQL_TIMEOUT_SECONDS,
                )
                rows = await cur.fetchmany(settings.DATA_QUERY_SQL_MAX_ROWS)
    except asyncio.TimeoutError:
        logger.warning("data_query_run_sql_timeout", timeout=settings.DATA_QUERY_SQL_TIMEOUT_SECONDS)
        return f"Error: query exceeded {settings.DATA_QUERY_SQL_TIMEOUT_SECONDS}s timeout. Narrow the WHERE clause."
    except Exception as e:
        logger.exception("data_query_run_sql_failed", error=str(e))
        return f"Error executing query: {e}"

    truncated_notice = (
        f"\n\n_(truncated at {settings.DATA_QUERY_SQL_MAX_ROWS} rows; add LIMIT or refine WHERE)_"
        if len(rows) >= settings.DATA_QUERY_SQL_MAX_ROWS
        else ""
    )
    logger.info("data_query_run_sql_completed", row_count=len(rows))
    return _format_rows(rows) + truncated_notice
