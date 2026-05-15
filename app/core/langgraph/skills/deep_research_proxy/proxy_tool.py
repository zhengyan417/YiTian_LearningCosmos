"""Proxy tool exposing the existing DeepResearchAgent as a single LangChain tool.

The underlying ``DeepResearchAgent`` owns its own PostgreSQL connection pool
and compiled sub-graph. We hold a module-level instance so the pool is built
once per process and reused across LLM-triggered invocations.
"""

from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.langgraph.deep_research import DeepResearchAgent
from app.core.logging import logger

_agent: Optional[DeepResearchAgent] = None


def _get_agent() -> DeepResearchAgent:
    """Return the lazy module-level DeepResearchAgent."""
    global _agent
    if _agent is None:
        _agent = DeepResearchAgent()
    return _agent


async def warm_up() -> None:
    """Pre-build the underlying graph and pool so the first LLM invocation isn't a cold start."""
    await _get_agent().create_graph()
    logger.info("deep_research_proxy_warmed_up")


async def shutdown() -> None:
    """Close the proxy agent's PostgreSQL pool on application shutdown."""
    global _agent
    if _agent is not None and _agent._connection_pool is not None:
        await _agent._connection_pool.close()
        logger.info("deep_research_proxy_pool_closed")
    _agent = None


@tool(parse_docstring=True)
async def deep_research(query: str, config: RunnableConfig) -> str:
    """Run a deep, multi-step research workflow on a complex question.

    HEAVY OPERATION — kicks off planning, parallel sub-agent searches, and
    synthesis. Typically takes 30-90 seconds and consumes significantly more
    tokens than a single ``tavily_search``. Only use it when the user explicitly
    asks for in-depth research, multi-source comparison, or a structured report.
    For simple factual lookups, prefer ``tavily_search``.

    Args:
        query: The research question to investigate end-to-end.
        config: LangGraph-injected runtime config; not user-visible (RunnableConfig
            is an InjectedToolArg and is hidden from the LLM tool schema).

    Returns:
        A markdown research report with citations, or an error description on failure.
    """
    parent_thread = (config.get("configurable") or {}).get("thread_id", "unknown")
    user_id = (config.get("metadata") or {}).get("user_id")
    sub_thread = f"deepresearch-sub-{parent_thread}"
    logger.info(
        "deep_research_proxy_invoked",
        parent_thread_id=parent_thread,
        sub_thread_id=sub_thread,
    )
    try:
        report = await _get_agent().run(query=query, thread_id=sub_thread, user_id=user_id)
        logger.info(
            "deep_research_proxy_completed",
            sub_thread_id=sub_thread,
            report_chars=len(report),
        )
        return report
    except Exception as e:
        logger.exception(
            "deep_research_proxy_failed",
            error=str(e),
            parent_thread_id=parent_thread,
        )
        return f"Deep research failed: {e}. Consider falling back to tavily_search for a lighter-weight answer."
