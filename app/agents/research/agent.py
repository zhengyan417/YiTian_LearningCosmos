"""Deep research orchestrator graph.

Flow:
    plan -> dispatch -> synthesize -> END

- ``plan`` instructs the LLM to output JSON with research sub-tasks and
  parses the response into a ``ResearchPlan``.
- ``dispatch`` runs the researcher sub-graph concurrently for each task,
  capped at ``RESEARCH_MAX_CONCURRENT_SUBAGENTS``.
- ``synthesize`` consolidates the sub-agent findings into a single markdown
  report with unified citations.
"""

import asyncio
import json
from typing import Optional
from urllib.parse import quote_plus

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import (
    END,
    StateGraph,
)
from langgraph.graph.state import (
    Command,
    CompiledStateGraph,
)
from psycopg import AsyncConnection
from psycopg.rows import (
    DictRow,
    dict_row,
)
from psycopg_pool import AsyncConnectionPool

from app.agents.base import (
    load_prompt,
    now_str,
)
from app.agents.research.researcher import run_researcher
from app.agents.research.state import (
    DeepResearchState,
    ResearchPlan,
)
from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.core.observability import get_langfuse_callback_handler
from app.services.llm import llm_service
from app.utils import extract_json


def _planner_prompt() -> str:
    """Load the research planner prompt with run-time variables inlined."""
    return load_prompt(__file__, "planner.md").format(
        current_date_and_time=now_str(),
        max_subtasks=settings.RESEARCH_MAX_SUBTASKS,
    )


def _synthesis_prompt(research_request: str, findings: str) -> str:
    """Load the research synthesis prompt with the original request and findings inlined."""
    return load_prompt(__file__, "synthesis.md").format(
        current_date_and_time=now_str(),
        research_request=research_request,
        findings=findings,
    )


PostgresConnPool = AsyncConnectionPool[AsyncConnection[DictRow]]


class ResearchAgent:
    """Orchestrator for the multi-agent deep research workflow."""

    def __init__(self) -> None:
        """Initialize the deep research agent with deferred graph creation."""
        self._connection_pool: Optional[PostgresConnPool] = None
        self._graph: Optional[CompiledStateGraph] = None
        logger.info(
            "deep_research_agent_initialized",
            model=settings.DEFAULT_LLM_MODEL,
            max_concurrent=settings.RESEARCH_MAX_CONCURRENT_SUBAGENTS,
            max_subtasks=settings.RESEARCH_MAX_SUBTASKS,
        )

    async def _get_connection_pool(self) -> Optional[PostgresConnPool]:
        if self._connection_pool is None:
            try:
                connection_url = (
                    "postgresql://"
                    f"{quote_plus(settings.POSTGRES_USER)}:{quote_plus(settings.POSTGRES_PASSWORD)}"
                    f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
                )
                self._connection_pool = AsyncConnectionPool(
                    connection_url,
                    open=False,
                    max_size=settings.POSTGRES_POOL_SIZE,
                    kwargs={
                        "autocommit": True,
                        "connect_timeout": 5,
                        "prepare_threshold": None,
                        "row_factory": dict_row,
                    },
                )
                await self._connection_pool.open()
                logger.info("research_connection_pool_created")
            except Exception as e:
                logger.error("research_connection_pool_creation_failed", error=str(e))
                if settings.ENVIRONMENT == Environment.PRODUCTION:
                    return None
                raise e
        return self._connection_pool

    async def _plan(self, state: DeepResearchState) -> Command:
        """Decompose the user's request into focused research sub-tasks."""
        request_msg = state.messages[-1] if state.messages else None
        request_text = str(request_msg.content) if request_msg is not None and request_msg.content else ""
        if not request_text:
            raise ValueError("research request is empty")

        messages = [
            SystemMessage(content=_planner_prompt()),
            HumanMessage(content=f"Research request:\n\n{request_text}"),
        ]

        with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
            response = await llm_service.call(messages, model_name=settings.DEFAULT_LLM_MODEL)

        raw = str(response.content) if response.content else "{}"
        try:
            plan_data = json.loads(extract_json(raw))
            tasks_raw = plan_data.get("tasks", [request_text])
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("failed_to_parse_plan_json", raw=raw[:500], error=str(e))
            tasks_raw = [request_text]

        plan = ResearchPlan(tasks=tasks_raw)

        tasks = list(plan.tasks)[: settings.RESEARCH_MAX_SUBTASKS]
        logger.info("research_plan_generated", task_count=len(tasks))

        return Command(
            update={"research_request": request_text, "research_tasks": tasks},
            goto="dispatch",
        )

    async def _dispatch(self, state: DeepResearchState) -> Command:
        """Run each planned task in a researcher sub-graph, bounded concurrency."""
        semaphore = asyncio.Semaphore(settings.RESEARCH_MAX_CONCURRENT_SUBAGENTS)

        async def _bounded(task: str) -> str:
            async with semaphore:
                try:
                    return await run_researcher(task)
                except Exception as e:
                    logger.exception("research_subagent_failed", task=task, error=str(e))
                    return f"Sub-agent for task '{task}' failed: {str(e)}"

        findings = list(await asyncio.gather(*[_bounded(t) for t in state.research_tasks]))
        logger.info("research_dispatch_complete", findings_count=len(findings))

        return Command(update={"findings": findings}, goto="synthesize")

    async def _synthesize(self, state: DeepResearchState) -> Command:
        """Consolidate sub-agent findings into a single final report."""
        joined = "\n\n---\n\n".join(f"### Sub-agent finding {i + 1}\n\n{f}" for i, f in enumerate(state.findings))

        prompt = _synthesis_prompt(
            research_request=state.research_request,
            findings=joined,
        )

        with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
            response = await llm_service.call([SystemMessage(content=prompt)], model_name=settings.DEFAULT_LLM_MODEL)

        report = str(response.content) if response.content else ""
        logger.info("research_report_synthesized", report_chars=len(report))

        return Command(
            update={
                "final_report": report,
                "messages": [AIMessage(content=report)],
            },
            goto=END,
        )

    async def create_graph(self) -> Optional[CompiledStateGraph]:
        """Build the orchestrator graph with PostgreSQL checkpointing."""
        if self._graph is not None:
            return self._graph

        try:
            builder = StateGraph(DeepResearchState)
            builder.add_node("plan", self._plan, destinations=("dispatch",))
            builder.add_node("dispatch", self._dispatch, destinations=("synthesize",))
            builder.add_node("synthesize", self._synthesize, destinations=(END,))
            builder.set_entry_point("plan")
            builder.set_finish_point("synthesize")

            connection_pool = await self._get_connection_pool()
            if connection_pool:
                checkpointer = AsyncPostgresSaver(connection_pool)
                await checkpointer.setup()
            else:
                checkpointer = None
                if settings.ENVIRONMENT != Environment.PRODUCTION:
                    raise Exception("Connection pool initialization failed")

            self._graph = builder.compile(
                checkpointer=checkpointer,
                name=f"{settings.PROJECT_NAME} Deep Research ({settings.ENVIRONMENT.value})",
            )
            logger.info("deep_research_graph_created", has_checkpointer=checkpointer is not None)
        except Exception as e:
            logger.error("deep_research_graph_creation_failed", error=str(e))
            if settings.ENVIRONMENT == Environment.PRODUCTION:
                return None
            raise e

        return self._graph

    async def _get_graph(self) -> CompiledStateGraph:
        if self._graph is None:
            self._graph = await self.create_graph()
        if self._graph is None:
            raise RuntimeError("deep research graph initialization failed")
        return self._graph

    async def run(self, task: str, context_id: str) -> str:
        """Execute the deep research workflow end-to-end.

        Args:
            task: The user's research request.
            context_id: Correlation id (used as the checkpoint thread id).

        Returns:
            The final synthesized markdown report.
        """
        graph = await self._get_graph()
        callbacks: list[BaseCallbackHandler] = (
            [get_langfuse_callback_handler()] if settings.LANGFUSE_TRACING_ENABLED else []
        )
        thread_id = f"research-{context_id}"
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "callbacks": callbacks,
            "metadata": {
                "thread_id": thread_id,
                "workflow": "deep_research",
                "environment": settings.ENVIRONMENT.value,
            },
        }

        try:
            final_state = await graph.ainvoke(
                input={"messages": [HumanMessage(content=task)]},
                config=config,
            )
            report = final_state.get("final_report", "")
            if not report:
                raise RuntimeError("deep research produced an empty report")
            return str(report)
        except Exception as e:
            logger.exception("research_agent_run_failed", thread_id=thread_id, error=str(e))
            raise


# Module-level singleton consumed by AGENT_REGISTRY.
research_agent = ResearchAgent()
