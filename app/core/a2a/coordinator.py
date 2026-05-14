"""The Coordinator agent — an A2A client that routes work to specialist servers.

Flow per request:
    1. route      — an LLM call classifies the request into specialist delegations
                    (or answers it directly).
    2. dispatch   — delegations run concurrently, each an A2A call to a specialist.
    3. synthesize — an LLM call merges the specialist results into one answer.
"""

import asyncio
import json

from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
)

from app.core.a2a.client import a2a_specialist_client
from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.core.prompts import (
    load_a2a_coordinator_router_prompt,
    load_a2a_coordinator_synthesis_prompt,
)
from app.schemas.multi_agent import (
    AgentResult,
    Delegation,
    MultiAgentResponse,
    RoutingDecision,
)
from app.services.llm import llm_service
from app.utils import extract_json


class CoordinatorAgent:
    """Routes user requests to A2A specialist agents and synthesizes their results."""

    async def run(self, query: str, context_id: str) -> MultiAgentResponse:
        """Handle one user request end-to-end.

        Args:
            query: The user's request.
            context_id: A2A context id correlating all specialist calls.

        Returns:
            The synthesized multi-agent response.
        """
        decision = await self._route(query)

        if not decision.delegations:
            answer = decision.direct_answer or "I'm not sure how to help with that yet."
            logger.info("a2a_coordinator_direct_answer", context_id=context_id)
            return MultiAgentResponse(answer=answer, routing_reasoning=decision.reasoning, delegations=[])

        results = await self._dispatch(decision.delegations, context_id)
        answer = await self._synthesize(query, results)
        return MultiAgentResponse(answer=answer, routing_reasoning=decision.reasoning, delegations=results)

    def _parse_routing_json(self, raw: str) -> RoutingDecision:
        """Parse the coordinator's JSON response into a RoutingDecision.

        Uses the shared ``extract_json`` utility to strip markdown code fences
        and non-JSON text. Falls back to a single research delegation on parse failure.

        Args:
            raw: The raw string content from the LLM response.

        Returns:
            The parsed routing decision.
        """
        text = extract_json(raw)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("a2a_coordinator_routing_json_parse_failed", raw=raw[:200])
            return RoutingDecision(
                reasoning="routing json parse failed; defaulting to a single research delegation",
                delegations=[Delegation(agent="research", task=raw[:500])],
            )

        data.setdefault("reasoning", "")
        data.setdefault("direct_answer", None)
        data.setdefault("delegations", [])
        return RoutingDecision.model_validate(data)

    async def _route(self, query: str) -> RoutingDecision:
        """Classify the request into specialist delegations via an LLM call.

        Uses JSON mode (response_format type=json_object) instead of structured
        output because the configured LLM provider may not support json_schema.
        Falls back to a single research delegation when routing fails.

        Args:
            query: The user's request.

        Returns:
            The routing decision.
        """
        messages = [
            SystemMessage(content=load_a2a_coordinator_router_prompt()),
            HumanMessage(content=query),
        ]
        try:
            with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
                response = await llm_service.call(
                    messages,
                    model_kwargs={"response_format": {"type": "json_object"}},
                )
        except Exception as e:
            logger.warning("a2a_coordinator_routing_failed_fallback_research", error=str(e))
            return RoutingDecision(
                reasoning="routing failed; defaulting to a single research delegation",
                delegations=[Delegation(agent="research", task=query)],
            )

        raw_content = str(response.content) if response.content else ""
        decision = self._parse_routing_json(raw_content)

        logger.info(
            "a2a_coordinator_routed",
            delegation_count=len(decision.delegations),
            direct=decision.direct_answer is not None,
        )
        return decision

    async def _dispatch(self, delegations: list[Delegation], context_id: str) -> list[AgentResult]:
        """Run all delegations concurrently as A2A calls, bounded by a semaphore.

        Args:
            delegations: The specialist delegations to execute.
            context_id: A2A context id for all calls.

        Returns:
            One AgentResult per delegation, in the original order.
        """
        semaphore = asyncio.Semaphore(settings.A2A_COORDINATOR_MAX_PARALLEL)

        async def _run_one(delegation: Delegation) -> AgentResult:
            async with semaphore:
                try:
                    output = await a2a_specialist_client.call(delegation.agent, delegation.task, context_id)
                except Exception as e:
                    logger.exception(
                        "a2a_coordinator_delegation_failed",
                        agent=delegation.agent,
                        error=str(e),
                    )
                    output = f"[{delegation.agent} agent unavailable: {e}]"
                return AgentResult(agent=delegation.agent, task=delegation.task, output=output)

        results = await asyncio.gather(*[_run_one(d) for d in delegations])
        logger.info("a2a_coordinator_dispatch_complete", result_count=len(results))
        return results

    async def _synthesize(self, query: str, results: list[AgentResult]) -> str:
        """Merge specialist results into one final answer via an LLM call.

        Args:
            query: The original user request.
            results: The specialist results to merge.

        Returns:
            The final synthesized answer (falls back to the raw findings on empty output).
        """
        findings = "\n\n---\n\n".join(
            f"### {result.agent} agent\nTask: {result.task}\n\n{result.output}" for result in results
        )
        prompt = load_a2a_coordinator_synthesis_prompt(query=query, findings=findings)
        with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
            response = await llm_service.call([SystemMessage(content=prompt)])
        report = str(response.content) if response.content else ""
        return report or findings


# Module-level singleton consumed by the coordinator API endpoint.
coordinator_agent = CoordinatorAgent()
