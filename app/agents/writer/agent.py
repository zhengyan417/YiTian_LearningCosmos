"""Writer agent — drafts or rewrites text.

A minimal one-node LangGraph: ``draft -> END``. The LLM call goes through the
LLMService one-off path (``model_name`` passed explicitly) so it never inherits
tool bindings from any other graph.
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
from app.agents.writer.state import WriterState
from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.services.llm import llm_service


def _system_prompt() -> str:
    """Load the writer system prompt with the current date inlined."""
    return load_prompt(__file__, "system.md").format(current_date_and_time=now_str())


class WriterAgent:
    """Single-node LangGraph that turns a writing task into drafted text."""

    def __init__(self) -> None:
        """Initialize the writer agent with deferred graph compilation."""
        self._graph: Optional[CompiledStateGraph] = None

    async def _draft(self, state: WriterState) -> Command:
        """One LLM call that produces the drafted text."""
        messages = [
            SystemMessage(content=_system_prompt()),
            HumanMessage(content=state.task),
        ]
        with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
            response = await llm_service.call(messages, model_name=settings.DEFAULT_LLM_MODEL)
        output = str(response.content).strip() if response.content else ""
        if not output:
            logger.warning("writer_agent_empty_output")
            output = "No output produced."
        return Command(update={"output": output}, goto=END)

    def create_graph(self) -> CompiledStateGraph:
        """Build and cache the writer LangGraph."""
        if self._graph is not None:
            return self._graph
        builder = StateGraph(WriterState)
        builder.add_node("draft", self._draft, destinations=(END,))
        builder.set_entry_point("draft")
        self._graph = builder.compile(name="Writer Agent")
        logger.info("writer_agent_graph_compiled")
        return self._graph

    async def run(self, task: str, context_id: str) -> str:
        """Run the writer graph end-to-end and return the drafted text."""
        logger.info("writer_agent_run_start", context_id=context_id)
        graph = self.create_graph()
        final_state = await graph.ainvoke({"task": task})
        return str(final_state.get("output", "No output produced."))


# Module-level singleton consumed by AGENT_REGISTRY.
writer_agent = WriterAgent()
