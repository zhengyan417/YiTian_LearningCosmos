"""Researcher sub-graph for the deep research workflow.

Uses a two-shot design to avoid DeepSeek ``reasoning_content`` issues:
1. First call — LLM decides search queries (text, no tool calls).
2. Execute searches in parallel.
3. Second call — LLM writes findings from the search results (fresh conversation).
"""

import asyncio
import json
from typing import Optional

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)
from langgraph.graph import (
    END,
    StateGraph,
)
from langgraph.graph.state import (
    Command,
    CompiledStateGraph,
)

from app.core.config import settings
from app.core.langgraph.deep_research.schemas import ResearcherState
from app.core.langgraph.tools import research_tools
from app.core.logging import logger
from app.core.prompts import load_research_subagent_prompt
from app.services.llm import LLMRegistry
from app.utils import extract_json

_tools_by_name = {t.name: t for t in research_tools}

_PLANNER_PROMPT_TEMPLATE = """\
{system_prompt}

Based on the research task, decide which searches to run. Reply with ONLY a JSON object:

```json
{{"searches": ["query 1", "query 2", ...], "reflection": "optional strategy note"}}
```

Max {max_searches} searches. Use 1-2 searches for simple queries, more only for complex ones."""


def _build_llm():
    """Build an LLM for the researcher (no tool binding — we parse JSON manually)."""
    base = LLMRegistry.get(settings.DEFAULT_LLM_MODEL)
    return base


_llm = _build_llm()


async def _researcher_plan(state: ResearcherState) -> Command:
    """Decide which searches to run based on the research task."""
    system_prompt = load_research_subagent_prompt()
    prompt = _PLANNER_PROMPT_TEMPLATE.format(
        system_prompt=system_prompt,
        max_searches=settings.RESEARCH_MAX_SEARCHES_PER_SUBAGENT,
    )

    llm = _llm
    response = await llm.ainvoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Research task: {state.task}"),
        ]
    )

    raw = str(response.content) if response.content else "{}"
    try:
        data = json.loads(extract_json(raw))
    except (json.JSONDecodeError, KeyError):
        data = {}
    searches = data.get("searches", [state.task])

    return Command(
        update={
            "messages": [AIMessage(content=f"Planned searches: {json.dumps(searches)}")],
            "search_count": 0,
            "pending_searches": searches,
        },
        goto="researcher_search",
    )


async def _researcher_search(state: ResearcherState) -> Command:
    """Execute pending searches in parallel."""
    searches = getattr(state, "pending_searches", [])
    tavily_tool = _tools_by_name.get("tavily_search")

    results: list[str] = []
    if tavily_tool and searches:

        async def _run_one(query: str) -> str:
            try:
                result = await tavily_tool.ainvoke({"query": query})
                return f"## Search: {query}\n\n{result}"
            except Exception as e:
                logger.warning("researcher_search_failed", query=query, error=str(e))
                return f"## Search: {query}\n\nFailed: {str(e)}"

        results = list(await asyncio.gather(*[_run_one(q) for q in searches]))

    return Command(
        update={
            "search_results": results,
            "search_count": len(searches),
        },
        goto="researcher_synthesize",
    )


async def _researcher_synthesize(state: ResearcherState) -> Command:
    """Synthesize findings from search results (fresh conversation, no history)."""
    search_results = state.search_results
    joined = "\n\n---\n\n".join(search_results) if search_results else "No search results."

    prompt = load_research_subagent_prompt()

    llm = _llm
    response = await llm.ainvoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(
                content=f"Research task: {state.task}\n\nSearch results:\n\n{joined}\n\nProduce your findings now in the required format."
            ),
        ]
    )

    raw = str(response.content) if response.content else "No findings produced."
    return Command(
        update={"messages": [AIMessage(content=raw)]},
        goto=END,
    )


_compiled_graph: Optional[CompiledStateGraph] = None


def get_researcher_graph() -> CompiledStateGraph:
    """Return the compiled researcher sub-graph (built once on first access)."""
    global _compiled_graph
    if _compiled_graph is None:
        builder = StateGraph(ResearcherState)
        builder.add_node("researcher_plan", _researcher_plan, destinations=("researcher_search",))
        builder.add_node("researcher_search", _researcher_search, destinations=("researcher_synthesize",))
        builder.add_node("researcher_synthesize", _researcher_synthesize, destinations=(END,))
        builder.set_entry_point("researcher_plan")
        builder.set_finish_point("researcher_synthesize")
        _compiled_graph = builder.compile(name="Researcher Sub-Agent")
        logger.info("researcher_graph_compiled")
    return _compiled_graph


async def run_researcher(task: str) -> str:
    """Run a single research task end-to-end and return the final findings text."""
    graph = get_researcher_graph()
    final_state = await graph.ainvoke({"task": task, "search_count": 0})

    messages = final_state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return "No findings produced."
