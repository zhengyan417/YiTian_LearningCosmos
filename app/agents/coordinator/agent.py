"""Coordinator agent — routes work to A2A specialists, then synthesizes.

LangGraph shape: ``route -> dispatch -> synthesize -> END``. When the route
node produces a ``direct_answer`` (no specialist needed), dispatch and
synthesize are skipped and the graph goes straight to END.

The coordinator is the A2A *client*; it never gets mounted as an A2A server.
It speaks to the four specialists through ``a2a_specialist_client`` so the
specialist agents stay fully decoupled (each lives behind its own A2A
endpoint).
"""

import asyncio
import json
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
from app.agents.coordinator.state import CoordinatorState
from app.core.a2a.client import a2a_specialist_client
from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.schemas.multi_agent import (
    AgentResult,
    Delegation,
    MultiAgentResponse,
    RoutingDecision,
)
from app.services.llm import llm_service
from app.utils import extract_json

# Human-readable section labels for the structured answer. Unknown agents fall
# back to a title-cased name.
_AGENT_LABELS: dict[str, str] = {
    "research": "Research",
    "search": "Search Results",
    "writer": "Written Draft",
    "coder": "Code & Implementation",
}

# Substrings that mark a specialist output as a failure rather than a real
# result. Checked case-insensitively.
_FAILURE_MARKERS: tuple[str, ...] = (
    "agent unavailable",
    "agent failed",
    "timed out",
    "no output produced",
    "no answer produced",
    "no relevant information was found",
)


def _router_prompt() -> str:
    """Load the coordinator router prompt with the current date inlined."""
    return load_prompt(__file__, "router.md").format(current_date_and_time=now_str())


def _synthesis_prompt(query: str, findings: str, failure_summary: str) -> str:
    """Load the coordinator synthesis prompt with all variables inlined."""
    return load_prompt(__file__, "synthesis.md").format(
        current_date_and_time=now_str(),
        query=query,
        findings=findings,
        failure_summary=failure_summary,
    )


def _is_failed_output(output: str) -> bool:
    """Return True if the specialist output reads as a failure."""
    if not output:
        return True
    lower = output.lower()
    return any(marker in lower for marker in _FAILURE_MARKERS)


def _agent_label(agent: str) -> str:
    """Return the human-readable section label for a specialist agent."""
    return _AGENT_LABELS.get(agent, agent.replace("_", " ").title())


class CoordinatorAgent:
    """Three-node LangGraph: ``route -> dispatch -> synthesize -> END``."""

    def __init__(self) -> None:
        """Initialize the coordinator with deferred graph compilation."""
        self._graph: Optional[CompiledStateGraph] = None

    # ------------------------------------------------------------------
    # Graph nodes
    # ------------------------------------------------------------------

    async def _route(self, state: CoordinatorState) -> Command:
        """Classify the request into specialist delegations via one LLM call."""
        messages = [
            SystemMessage(content=_router_prompt()),
            HumanMessage(content=state.query),
        ]
        try:
            with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
                response = await llm_service.call(
                    messages,
                    model_kwargs={"response_format": {"type": "json_object"}},
                )
            decision = self._parse_routing_json(str(response.content) if response.content else "")
        except Exception as e:
            logger.warning("coordinator_routing_failed_fallback_research", error=str(e))
            decision = RoutingDecision(
                reasoning="routing failed; defaulting to a single research delegation",
                delegations=[Delegation(agent="research", task=state.query)],
            )

        logger.info(
            "coordinator_routed",
            delegation_count=len(decision.delegations),
            direct=decision.direct_answer is not None,
        )

        # If the router gave a direct answer, skip dispatch+synthesize entirely.
        if not decision.delegations:
            answer = decision.direct_answer or "I'm not sure how to help with that yet."
            return Command(
                update={
                    "routing_reasoning": decision.reasoning,
                    "direct_answer": decision.direct_answer,
                    "delegations": [],
                    "answer": answer,
                },
                goto=END,
            )

        return Command(
            update={
                "routing_reasoning": decision.reasoning,
                "direct_answer": None,
                "delegations": decision.delegations,
            },
            goto="dispatch",
        )

    async def _dispatch(self, state: CoordinatorState) -> Command:
        """Run all delegations concurrently as A2A calls, bounded by a semaphore."""
        semaphore = asyncio.Semaphore(settings.A2A_COORDINATOR_MAX_PARALLEL)

        async def _run_one(delegation: Delegation) -> AgentResult:
            async with semaphore:
                try:
                    output = await a2a_specialist_client.call(
                        delegation.agent,
                        delegation.task,
                        state.context_id,
                    )
                except Exception as e:
                    logger.exception(
                        "coordinator_delegation_failed",
                        agent=delegation.agent,
                        error=str(e),
                    )
                    output = f"[{delegation.agent} agent unavailable: {e}]"
                return AgentResult(agent=delegation.agent, task=delegation.task, output=output)

        results = list(await asyncio.gather(*[_run_one(d) for d in state.delegations]))
        logger.info("coordinator_dispatch_complete", result_count=len(results))
        return Command(update={"results": results}, goto="synthesize")

    async def _synthesize(self, state: CoordinatorState) -> Command:
        """Produce the final answer: brief LLM intro + verbatim specialist outputs."""
        findings = "\n\n---\n\n".join(f"### {r.agent} agent\nTask: {r.task}\n\n{r.output}" for r in state.results)
        failure_summary = self._build_failure_summary(state.results)
        prompt = _synthesis_prompt(query=state.query, findings=findings, failure_summary=failure_summary)

        intro = ""
        try:
            with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
                response = await llm_service.call(
                    [SystemMessage(content=prompt)],
                    model_name=settings.DEFAULT_LLM_MODEL,
                )
            intro = str(response.content).strip() if response.content else ""
        except Exception:
            logger.exception("coordinator_synthesis_llm_failed_using_default_intro")

        if not intro:
            logger.warning("coordinator_synthesis_empty_intro_using_default", findings_chars=len(findings))

        answer = self._assemble_structured_response(state.results, intro)
        return Command(update={"answer": answer}, goto=END)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_routing_json(self, raw: str) -> RoutingDecision:
        """Parse the router LLM's JSON response into a RoutingDecision."""
        text = extract_json(raw)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("coordinator_routing_json_parse_failed", raw=raw[:200])
            return RoutingDecision(
                reasoning="routing json parse failed; defaulting to a single research delegation",
                delegations=[Delegation(agent="research", task=raw[:500])],
            )
        data.setdefault("reasoning", "")
        data.setdefault("direct_answer", None)
        data.setdefault("delegations", [])
        return RoutingDecision.model_validate(data)

    def _build_failure_summary(self, results: list[AgentResult]) -> str:
        """Build a markdown summary of which specialists succeeded and failed.

        Used by the synthesizer prompt so the LLM-written intro can mention
        failures honestly. Returns an empty string when every specialist succeeded.
        """
        succeeded: list[str] = []
        failed: list[str] = []
        for r in results:
            if _is_failed_output(r.output):
                failed.append(r.agent)
            else:
                succeeded.append(r.agent)

        if not failed:
            return ""

        parts = ["## Specialist Status"]
        if succeeded:
            parts.append(f"- Succeeded: {', '.join(succeeded)}")
        parts.append(f"- Failed: {', '.join(failed)}")
        parts.append("")
        parts.append(
            "Mention the failed parts honestly in your overview — explain what could not "
            "be looked up and suggest the user retry. Do not invent results for failed agents."
        )
        return "\n".join(parts)

    def _assemble_structured_response(self, results: list[AgentResult], intro: str) -> str:
        r"""Build the final answer text: intro paragraph + per-specialist sections.

        Specialist outputs are kept verbatim under cleanly-named H2 headers, so
        the user-facing answer never leaks raw internal markers like
        ``### research agent\nTask: ...``. Failed specialists get an italicized
        explanation in place of their (often error-message) output.
        """
        succeeded = [r for r in results if not _is_failed_output(r.output)]
        failed = [r for r in results if _is_failed_output(r.output)]
        n_total = len(results)
        n_ok = len(succeeded)

        parts: list[str] = []
        if intro:
            parts.append(intro)
        elif n_ok == 0:
            parts.append(
                f"I wasn't able to complete any of the {n_total} parts of your request. "
                "Please try a simpler request or try again in a moment."
            )
        elif failed:
            missing = ", ".join(_agent_label(r.agent) for r in failed)
            parts.append(
                f"Here are the results for your {n_total}-part request. "
                f"{n_ok} of {n_total} parts completed; the rest ({missing}) "
                "could not be completed and is noted in its section below."
            )
        else:
            parts.append(f"Here are the results for your {n_total}-part request — all sections completed.")

        parts.append("---")

        for r in results:
            parts.append(f"## {_agent_label(r.agent)}")
            parts.append(f"*{r.task}*")
            if _is_failed_output(r.output):
                parts.append(f"_{r.output or 'No output was produced.'}_")
            else:
                parts.append(r.output)

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_graph(self) -> CompiledStateGraph:
        """Build and cache the coordinator's LangGraph."""
        if self._graph is not None:
            return self._graph
        builder = StateGraph(CoordinatorState)
        builder.add_node("route", self._route, destinations=("dispatch", END))
        builder.add_node("dispatch", self._dispatch, destinations=("synthesize",))
        builder.add_node("synthesize", self._synthesize, destinations=(END,))
        builder.set_entry_point("route")
        self._graph = builder.compile(name="Coordinator Agent")
        logger.info("coordinator_agent_graph_compiled")
        return self._graph

    async def run_full(self, task: str, context_id: str) -> MultiAgentResponse:
        """Run the coordinator graph and return the full structured response.

        Used by the ``/chat`` route which wants the answer + routing reasoning
        + per-specialist breakdown. The ``run`` variant below returns only the
        answer text to satisfy the uniform Agent protocol.
        """
        logger.info("coordinator_run_start", context_id=context_id, query_chars=len(task))
        graph = self.create_graph()
        final_state = await graph.ainvoke({"query": task, "context_id": context_id})
        return MultiAgentResponse(
            answer=str(final_state.get("answer", "")),
            routing_reasoning=str(final_state.get("routing_reasoning", "")),
            delegations=final_state.get("results", []),
        )

    async def run(self, task: str, context_id: str) -> str:
        """Protocol-compatible variant returning only the final answer text."""
        result = await self.run_full(task, context_id)
        return result.answer


# Module-level singleton consumed by AGENT_REGISTRY and the /chat route.
coordinator_agent = CoordinatorAgent()
