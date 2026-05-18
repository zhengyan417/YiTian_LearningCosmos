"""Search agent — one Tavily search + LLM summarization.

Two-node LangGraph: ``search -> summarize -> END``. The ``search`` node runs a
single Tavily query and stashes the raw markdown in the state; the ``summarize``
node turns those raw results into a concise, cited answer following the search
system prompt.
"""

from typing import Optional

from langchain_core.messages import (
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

from app.agents.base import (
    load_prompt,
    now_str,
)
from app.agents.search.state import SearchState
from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.services.llm import llm_service
from app.tools import tavily_search


def _system_prompt() -> str:
    """Load the search system prompt with the current date inlined."""
    return load_prompt(__file__, "system.md").format(current_date_and_time=now_str())


class SearchAgent:
    """Two-node LangGraph that turns a search query into a cited answer."""

    def __init__(self) -> None:
        """Initialize the search agent with deferred graph compilation."""
        self._graph: Optional[CompiledStateGraph] = None

    async def _search(self, state: SearchState) -> Command:
        """Run one Tavily search; record raw markdown for the summarize node."""
        try:
            raw = await tavily_search.ainvoke({"query": state.task})
        except Exception as e:
            logger.warning("search_agent_tavily_failed", error=str(e))
            raw = f"Search failed: {e}"
        return Command(update={"raw_results": str(raw)}, goto="summarize")

    async def _summarize(self, state: SearchState) -> Command:
        """Single LLM call that summarizes the raw results into a cited answer."""
        messages = [
            SystemMessage(content=_system_prompt()),
            HumanMessage(
                content=f"Search query:\n{state.task}\n\nRaw results:\n{state.raw_results}\n\nWrite the answer now.",
            ),
        ]
        with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
            response = await llm_service.call(messages, model_name=settings.DEFAULT_LLM_MODEL)
        output = str(response.content).strip() if response.content else ""
        if not output:
            logger.warning("search_agent_empty_output")
            output = "No answer produced."
        return Command(update={"output": output}, goto=END)

    def create_graph(self) -> CompiledStateGraph:
        """Build and cache the search LangGraph."""
        if self._graph is not None:
            return self._graph
        builder = StateGraph(SearchState)
        builder.add_node("search", self._search, destinations=("summarize",))
        builder.add_node("summarize", self._summarize, destinations=(END,))
        builder.set_entry_point("search")
        self._graph = builder.compile(name="Search Agent")
        logger.info("search_agent_graph_compiled")
        return self._graph

    async def run(self, task: str, context_id: str) -> str:
        """Run the search graph end-to-end and return the cited answer."""
        logger.info("search_agent_run_start", context_id=context_id)
        graph = self.create_graph()
        final_state = await graph.ainvoke({"task": task})
        return str(final_state.get("output", "No answer produced."))


# Module-level singleton consumed by AGENT_REGISTRY.
search_agent = SearchAgent()
