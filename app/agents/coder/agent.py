"""Coder agent — drafts a code answer, then runs a single critic review pass.

LangGraph shape: ``code → review → END``. When ``CODER_REFLECTION_ENABLED``
is off the ``code`` node fills ``output`` directly and short-circuits to END
(zero extra LLM calls). The ``review`` node runs at most once — there is **no
critic loop** — so the worst-case path is exactly two LLM calls per request.

Reflection design notes:

- The critic combines "evaluate" and "rewrite" into a single LLM call. It
  returns either ``{"verdict": "accept", ...}`` (we keep the draft) or
  ``{"verdict": "revise", "revised_output": "..."}`` (we replace the draft).
  Two calls instead of three keeps the latency/cost overhead bounded.
- Every failure mode in the review node (LLM raises, JSON parse fails, empty
  ``revised_output``) falls back to **keeping the draft** so a malformed
  critic response never poisons the answer the user sees.
- ``model_name`` is passed explicitly on both calls so the LLM service goes
  through the one-off path and never inherits any other graph's tool
  bindings — critical for the coder, which otherwise tends to emit
  ``finish_reason=tool_calls`` with empty content.
"""

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
from pydantic import (
    BaseModel,
    Field,
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
from app.utils import extract_json


def _system_prompt() -> str:
    """Load the coder system prompt with the current date inlined."""
    return load_prompt(__file__, "system.md").format(current_date_and_time=now_str())


def _review_prompt() -> str:
    """Load the coder review (critic) prompt with the current date inlined."""
    return load_prompt(__file__, "review.md").format(current_date_and_time=now_str())


class _ReviewDecision(BaseModel):
    """Parsed critic response. Defaults bias toward keeping the draft."""

    verdict: str = Field(default="accept")
    issues: str = Field(default="")
    revised_output: str = Field(default="")


class CoderAgent:
    """Two-node LangGraph: ``code → review → END`` (review skipped via config)."""

    def __init__(self) -> None:
        """Initialize the coder agent with deferred graph compilation."""
        self._graph: Optional[CompiledStateGraph] = None

    # ------------------------------------------------------------------
    # Graph nodes
    # ------------------------------------------------------------------

    async def _code(self, state: CoderState) -> Command:
        """First-pass draft. Skips review and goes straight to END when reflection is off."""
        messages = [
            SystemMessage(content=_system_prompt()),
            HumanMessage(content=state.task),
        ]
        with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
            response = await llm_service.call(messages, model_name=settings.DEFAULT_LLM_MODEL)
        draft = str(response.content).strip() if response.content else ""
        if not draft:
            logger.warning("coder_agent_empty_draft")
            draft = "No output produced."

        if not settings.CODER_REFLECTION_ENABLED:
            return Command(update={"draft": draft, "output": draft}, goto=END)

        return Command(update={"draft": draft}, goto="review")

    async def _review(self, state: CoderState) -> Command:
        """Single critic pass — accept the draft or replace it with a revised version.

        On any failure (LLM raises, JSON parse fails, empty revised_output)
        the original draft is kept so the user always receives an answer.
        """
        critic_input = (
            f"## Task\n\n{state.task}\n\n"
            f"## Draft answer\n\n{state.draft}\n\n"
            "Review the draft now and reply with the required JSON."
        )

        try:
            with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
                response = await llm_service.call(
                    [
                        SystemMessage(content=_review_prompt()),
                        HumanMessage(content=critic_input),
                    ],
                    model_name=settings.DEFAULT_LLM_MODEL,
                    model_kwargs={"response_format": {"type": "json_object"}},
                )
            decision = self._parse_review_json(str(response.content) if response.content else "")
        except Exception as e:
            logger.warning("coder_agent_review_failed_keeping_draft", error=str(e))
            return Command(
                update={"output": state.draft, "verdict": "accept", "issues": ""},
                goto=END,
            )

        revised = decision.revised_output.strip()
        if decision.verdict == "revise" and revised:
            logger.info(
                "coder_agent_review_revised",
                issue_chars=len(decision.issues),
                revised_chars=len(revised),
            )
            return Command(
                update={
                    "output": revised,
                    "verdict": "revise",
                    "issues": decision.issues,
                },
                goto=END,
            )

        # "accept", or a "revise" verdict with an empty revised_output — both
        # mean we ship the original draft unchanged.
        logger.info("coder_agent_review_accepted", parsed_verdict=decision.verdict)
        return Command(
            update={"output": state.draft, "verdict": "accept", "issues": ""},
            goto=END,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_review_json(self, raw: str) -> _ReviewDecision:
        """Best-effort parse of the critic's JSON response.

        Falls back to an ``accept`` decision (keep the draft) when parsing
        fails so a malformed critic response never blocks the answer.
        """
        text = extract_json(raw)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("coder_agent_review_json_parse_failed", raw=raw[:200])
            return _ReviewDecision()
        return _ReviewDecision.model_validate(
            {
                "verdict": data.get("verdict", "accept") or "accept",
                "issues": data.get("issues", "") or "",
                "revised_output": data.get("revised_output", "") or "",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_graph(self) -> CompiledStateGraph:
        """Build and cache the coder LangGraph."""
        if self._graph is not None:
            return self._graph
        builder = StateGraph(CoderState)
        builder.add_node("code", self._code, destinations=("review", END))
        builder.add_node("review", self._review, destinations=(END,))
        builder.set_entry_point("code")
        self._graph = builder.compile(name="Coder Agent")
        logger.info(
            "coder_agent_graph_compiled",
            reflection_enabled=settings.CODER_REFLECTION_ENABLED,
        )
        return self._graph

    async def run(self, task: str, context_id: str) -> str:
        """Run the coder graph end-to-end and return the final code answer."""
        logger.info(
            "coder_agent_run_start",
            context_id=context_id,
            reflection_enabled=settings.CODER_REFLECTION_ENABLED,
        )
        graph = self.create_graph()
        final_state = await graph.ainvoke({"task": task})
        return str(final_state.get("output", "No output produced."))


# Module-level singleton consumed by AGENT_REGISTRY.
coder_agent = CoderAgent()
