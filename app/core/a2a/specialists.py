"""Specialist agent logic behind the A2A servers.

Each specialist exposes a uniform ``async run(task, context_id) -> str`` signature
so the A2A executor stays a thin protocol adapter and the coordinator can treat
every remote agent identically. ``research`` reuses the existing deep research
workflow; ``search`` / ``writer`` / ``coder`` are direct LLM calls driven by their
own system prompts.
"""

from collections.abc import (
    Awaitable,
    Callable,
)

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from app.core.config import settings
from app.core.langgraph.deep_research import DeepResearchAgent
from app.core.langgraph.tools import duckduckgo_search_tool
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.core.prompts import (
    load_a2a_coder_prompt,
    load_a2a_search_prompt,
    load_a2a_writer_prompt,
)
from app.services.llm import llm_service

# Uniform specialist signature: (task, context_id) -> result text.
SpecialistRunner = Callable[[str, str], Awaitable[str]]

# The research specialist reuses the existing multi-agent deep research workflow.
# It owns its own DeepResearchAgent instance (and PostgreSQL checkpointer pool)
# so the A2A subsystem stays decoupled from the /research endpoint's instance.
_research_agent = DeepResearchAgent()


async def run_research(task: str, context_id: str) -> str:
    """Run the deep research workflow for an A2A research task.

    Args:
        task: The research question to investigate.
        context_id: A2A context id, used to derive a checkpointing thread id.

    Returns:
        The synthesized markdown research report.
    """
    logger.info("a2a_specialist_research_start", context_id=context_id)
    report = await _research_agent.run(query=task, thread_id=f"a2a-research-{context_id}")
    logger.info("a2a_specialist_research_complete", context_id=context_id, report_chars=len(report))
    return report


async def run_search(task: str, context_id: str) -> str:
    """Run a single web search and summarize the results into an answer.

    Args:
        task: The search query / narrow factual question.
        context_id: A2A context id for log correlation.

    Returns:
        A concise, cited answer derived from the search results.
    """
    logger.info("a2a_specialist_search_start", context_id=context_id)
    try:
        raw_results = await duckduckgo_search_tool.ainvoke(task)
    except Exception as e:
        logger.warning("a2a_specialist_search_tool_failed", context_id=context_id, error=str(e))
        raw_results = f"Search failed: {e}"

    messages = [
        SystemMessage(content=load_a2a_search_prompt()),
        HumanMessage(content=f"Search query:\n{task}\n\nRaw results:\n{raw_results}\n\nWrite the answer now."),
    ]
    with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
        response = await llm_service.call(messages)
    return str(response.content) if response.content else "No answer produced."


async def run_writer(task: str, context_id: str) -> str:
    """Summarize, rewrite, or reformat the supplied text.

    Args:
        task: The text plus transformation instructions.
        context_id: A2A context id for log correlation.

    Returns:
        The transformed text.
    """
    logger.info("a2a_specialist_writer_start", context_id=context_id)
    messages = [
        SystemMessage(content=load_a2a_writer_prompt()),
        HumanMessage(content=task),
    ]
    with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
        response = await llm_service.call(messages)
    return str(response.content) if response.content else "No output produced."


async def run_coder(task: str, context_id: str) -> str:
    """Answer a programming question or produce a code snippet.

    Args:
        task: The programming question or coding request.
        context_id: A2A context id for log correlation.

    Returns:
        The answer, including code blocks where relevant.
    """
    logger.info("a2a_specialist_coder_start", context_id=context_id)
    messages = [
        SystemMessage(content=load_a2a_coder_prompt()),
        HumanMessage(content=task),
    ]
    with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
        response = await llm_service.call(messages)
    return str(response.content) if response.content else "No output produced."


# Registry consumed by the A2A server factory — one executor is built per entry.
SPECIALIST_RUNNERS: dict[str, SpecialistRunner] = {
    "research": run_research,
    "search": run_search,
    "writer": run_writer,
    "coder": run_coder,
}


async def warm_up_specialists() -> None:
    """Pre-build the research specialist's graph to avoid first-request cold start."""
    await _research_agent.create_graph()


async def shutdown_specialists() -> None:
    """Release resources held by the specialists (the research checkpointer pool)."""
    if _research_agent._connection_pool is not None:
        await _research_agent._connection_pool.close()
        logger.info("a2a_research_connection_pool_closed")
