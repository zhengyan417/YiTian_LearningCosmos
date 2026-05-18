"""Coder agent — answers programming questions and writes code.

A minimal one-node LangGraph: ``code -> END``. Passes ``model_name`` to the LLM
service so it goes through the one-off path and never inherits any other graph's
tool bindings — critical for the coder, which otherwise tends to emit
``finish_reason=tool_calls`` with empty content.
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
from app.agents.coder.state import CoderState
from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.services.llm import llm_service


def _system_prompt() -> str:
    """Load the coder system prompt with the current date inlined."""
    return load_prompt(__file__, "system.md").format(current_date_and_time=now_str())


class CoderAgent:
    """Single-node LangGraph that turns a programming task into a code answer."""

    def __init__(self) -> None:
        """Initialize the coder agent with deferred graph compilation."""
        self._graph: Optional[CompiledStateGraph] = None

    async def _code(self, state: CoderState) -> Command:
        """One LLM call that produces the code answer."""
        messages = [
            SystemMessage(content=_system_prompt()),
            HumanMessage(content=state.task),
        ]
        with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
            response = await llm_service.call(messages, model_name=settings.DEFAULT_LLM_MODEL)
        output = str(response.content).strip() if response.content else ""
        if not output:
            logger.warning("coder_agent_empty_output")
            output = "No output produced."
        return Command(update={"output": output}, goto=END)

    def create_graph(self) -> CompiledStateGraph:
        """Build and cache the coder LangGraph."""
        if self._graph is not None:
            return self._graph
        builder = StateGraph(CoderState)
        builder.add_node("code", self._code, destinations=(END,))
        builder.set_entry_point("code")
        self._graph = builder.compile(name="Coder Agent")
        logger.info("coder_agent_graph_compiled")
        return self._graph

    async def run(self, task: str, context_id: str) -> str:
        """Run the coder graph end-to-end and return the code answer."""
        logger.info("coder_agent_run_start", context_id=context_id)
        graph = self.create_graph()
        final_state = await graph.ainvoke({"task": task})
        return str(final_state.get("output", "No output produced."))


# Module-level singleton consumed by AGENT_REGISTRY.
coder_agent = CoderAgent()
