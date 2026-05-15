"""Proxy tool exposing the A2A coordinator as a single LangChain tool.

Reuses the module-level ``coordinator_agent`` singleton, so this proxy adds no
new connection / pool overhead — it's a thin adapter from the LLM tool-calling
interface to ``CoordinatorAgent.run``.
"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from app.core.a2a.coordinator import coordinator_agent
from app.core.logging import logger


@tool(parse_docstring=True)
async def multi_agent_delegate(task: str, config: RunnableConfig) -> str:
    """Delegate a multi-domain task to the A2A coordinator.

    HEAVY OPERATION — the coordinator runs its own LLM router pass, then
    dispatches work to remote A2A specialists (research, search, writer, coder),
    then synthesizes their outputs. Only use this when a task spans 2+ specialist
    domains and would benefit from cross-agent collaboration. For single-domain
    work, call the appropriate skill (or its underlying tool) directly.

    Args:
        task: The multi-domain user task to delegate.
        config: LangGraph-injected runtime config; not user-visible (RunnableConfig
            is an InjectedToolArg and is hidden from the LLM tool schema).

    Returns:
        The synthesized answer from the coordinator, or an error description on failure.
    """
    parent_thread = (config.get("configurable") or {}).get("thread_id", "unknown")
    context_id = f"a2a-coord-{parent_thread}"
    logger.info(
        "multi_agent_proxy_invoked",
        parent_thread_id=parent_thread,
        context_id=context_id,
    )
    try:
        response = await coordinator_agent.run(query=task, context_id=context_id)
        logger.info(
            "multi_agent_proxy_completed",
            context_id=context_id,
            delegation_count=len(response.delegations),
            answer_chars=len(response.answer),
        )
        return response.answer
    except Exception as e:
        logger.exception(
            "multi_agent_proxy_failed",
            error=str(e),
            parent_thread_id=parent_thread,
        )
        return f"Multi-agent delegation failed: {e}. Consider answering directly or invoking a single skill instead."
