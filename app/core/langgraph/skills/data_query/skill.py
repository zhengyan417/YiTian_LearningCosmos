"""Data query skill — read-only SQL + whitelisted HTTP GET.

The skill is built dynamically: each tool is included only when its underlying
configuration is present. This keeps the LLM-visible surface honest — if there
is no SQL DSN configured, the LLM never sees ``run_sql`` and won't waste a turn
trying to use it.
"""

from typing import List

from langchain_core.tools.base import BaseTool

from app.core.config import settings
from app.core.langgraph.skills.base import Skill
from app.core.langgraph.skills.data_query.http_tool import http_api_call
from app.core.langgraph.skills.data_query.sql_tool import run_sql


def build_data_query_skill() -> Skill:
    """Assemble the data_query skill from the currently-enabled tools."""
    tools: List[BaseTool] = []
    capability_summary: List[str] = []

    if settings.DATA_QUERY_READONLY_DSN:
        tools.append(run_sql)
        capability_summary.append("read-only SQL against the analytics DB")

    if settings.DATA_QUERY_ALLOWED_HOSTS:
        tools.append(http_api_call)
        capability_summary.append("GET against whitelisted internal HTTP APIs")

    summary = "Internal data lookup: " + " + ".join(capability_summary)

    return Skill(
        name="data_query",
        summary=summary,
        when_to_use=(
            "The user asks about *internal* business data (orders, users, metrics) "
            "or the status of an *internal* service that exposes a JSON endpoint. "
            "Use SQL when the data lives in a relational table; use http_api_call "
            "when only an API exposes it."
        ),
        when_not_to_use=(
            "The user is asking about public-web information — use web_research instead. "
            "The query would write data — this skill is read-only and will reject writes. "
            "You don't actually know the table schema; ask_human first rather than guessing."
        ),
        examples=[
            "User: 'How many orders were placed yesterday?' → run_sql('SELECT count(*) FROM orders WHERE created_at >= current_date - 1')",
            "User: 'Is the billing service healthy?' → http_api_call('https://billing.internal/health')",
        ],
        tools=tools,
    )
