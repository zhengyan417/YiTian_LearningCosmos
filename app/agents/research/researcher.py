"""Researcher sub-graph for the deep research workflow.

Graph shape: ``plan → search ⇄ reflect → synthesize``.

- ``plan`` picks 1-3 opening search queries.
- ``search`` runs the current round's queries in parallel; results accumulate.
- ``reflect`` assesses the accumulated results and either queues follow-up
  searches (loop back to ``search``) or finishes (go to ``synthesize``).
- ``synthesize`` writes the findings from every accumulated result.

No native tool-calling is used anywhere — every LLM call is a plain JSON-mode
or text completion. This is deliberate: it sidesteps the DeepSeek
``reasoning_content`` issues that surface when tools are bound, and keeps the
loop's control flow in explicit graph edges rather than in the model.
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
from pydantic import (
    BaseModel,
    Field,
)

from app.agents.base import (
    load_prompt,
    now_str,
)
from app.agents.research.state import ResearcherState
from app.core.config import settings
from app.core.logging import logger
from app.core.metrics import llm_inference_duration_seconds
from app.services.llm import llm_service
from app.tools import tavily_search
from app.utils import extract_json

# Upper bound on the opening search batch the planner may produce. Follow-up
# searches are added later by the reflect node, bounded separately by
# settings.RESEARCH_MAX_SEARCHES_PER_SUBAGENT.
_MAX_OPENING_SEARCHES = 3

_JSON_MODE: dict = {"response_format": {"type": "json_object"}}

_PLANNER_PROMPT_TEMPLATE = """\
{system_prompt}

Decide the OPENING web searches for this research task. Later rounds can add
follow-up searches based on what these return, so keep this round broad.

Reply with ONLY a JSON object — no markdown, no code fences:
{{"searches": ["query 1", "query 2"]}}

Use 1 query for a simple task, 2-3 for a broad or multi-part task. Maximum 3."""


def _subagent_prompt() -> str:
    """Load the research sub-agent role prompt with the current date inlined."""
    return load_prompt(__file__, "subagent.md").format(current_date_and_time=now_str())


def _reflect_prompt() -> str:
    """Load the researcher reflection prompt with the current date inlined."""
    return load_prompt(__file__, "reflect.md").format(current_date_and_time=now_str())


class _ReflectionDecision(BaseModel):
    """Parsed reflect-node response. Defaults bias toward stopping the loop."""

    status: str = Field(default="stop")
    assessment: str = Field(default="")
    next_searches: list[str] = Field(default_factory=list)


def _parse_reflection_json(raw: str) -> _ReflectionDecision:
    """Best-effort parse of the reflect node's JSON response.

    Falls back to a ``stop`` decision when parsing fails so a malformed
    response can only ever end the loop, never extend it.
    """
    text = extract_json(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("researcher_reflect_json_parse_failed", raw=raw[:200])
        return _ReflectionDecision()

    raw_searches = data.get("next_searches", []) or []
    if isinstance(raw_searches, list):
        searches = [str(s).strip() for s in raw_searches if str(s).strip()]
    else:
        searches = []
    # Drop duplicates within the batch while preserving order.
    searches = list(dict.fromkeys(searches))

    return _ReflectionDecision(
        status=str(data.get("status", "stop") or "stop"),
        assessment=str(data.get("assessment", "") or ""),
        next_searches=searches,
    )


async def _researcher_plan(state: ResearcherState) -> Command:
    """Pick the opening web searches for the assigned research task."""
    prompt = _PLANNER_PROMPT_TEMPLATE.format(system_prompt=_subagent_prompt())
    messages = [
        SystemMessage(content=prompt),
        HumanMessage(content=f"Research task: {state.task}"),
    ]

    with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
        response = await llm_service.call(
            messages,
            model_name=settings.DEFAULT_LLM_MODEL,
            model_kwargs=_JSON_MODE,
        )

    raw = str(response.content) if response.content else "{}"
    try:
        data = json.loads(extract_json(raw))
        searches = data.get("searches", [state.task])
    except (json.JSONDecodeError, KeyError):
        logger.warning("researcher_plan_json_parse_failed", raw=raw[:200])
        searches = [state.task]

    if not isinstance(searches, list) or not searches:
        searches = [state.task]
    searches = [str(s).strip() for s in searches if str(s).strip()][:_MAX_OPENING_SEARCHES]
    if not searches:
        searches = [state.task]

    logger.info("researcher_plan_done", task=state.task[:80], opening_searches=len(searches))
    return Command(
        update={
            "messages": [AIMessage(content=f"Planned opening searches: {json.dumps(searches)}")],
            "pending_searches": searches,
        },
        goto="researcher_search",
    )


async def _researcher_search(state: ResearcherState) -> Command:
    """Execute the current round's pending searches in parallel.

    Results are appended to ``search_results`` via the state reducer, so this
    node returns only the current round's results.
    """
    searches = state.pending_searches

    async def _run_one(query: str) -> str:
        try:
            result = await tavily_search.ainvoke({"query": query})
            return f"## Search: {query}\n\n{result}"
        except Exception as e:
            logger.warning("researcher_search_failed", query=query, error=str(e))
            return f"## Search: {query}\n\nFailed: {str(e)}"

    results: list[str] = []
    if searches:
        results = list(await asyncio.gather(*[_run_one(q) for q in searches]))

    total = state.search_count + len(searches)
    logger.info("researcher_search_done", round_searches=len(searches), total_searches=total)
    return Command(
        update={
            "search_results": results,
            "search_count": total,
        },
        goto="researcher_reflect",
    )


async def _researcher_reflect(state: ResearcherState) -> Command:
    """Assess gathered results; queue follow-up searches or finish.

    Routes to ``researcher_search`` (continue) or ``researcher_synthesize``
    (stop). Every guard and every failure mode routes to synthesize, so a bad
    LLM response can only end the loop — it can never extend it.
    """
    rounds_done = len(state.reflection_notes)

    # Hard guards — these stop the loop regardless of what the LLM might say.
    if state.search_count >= settings.RESEARCH_MAX_SEARCHES_PER_SUBAGENT:
        logger.info("researcher_reflect_stop_search_cap", search_count=state.search_count)
        return Command(goto="researcher_synthesize")
    if rounds_done >= settings.RESEARCH_MAX_REFLECTION_ROUNDS:
        logger.info("researcher_reflect_stop_round_cap", rounds=rounds_done)
        return Command(goto="researcher_synthesize")

    joined = "\n\n---\n\n".join(state.search_results) if state.search_results else "No search results."
    reflect_input = (
        f"## Research task\n\n{state.task}\n\n"
        f"## Searches run so far: {state.search_count} "
        f"(hard cap {settings.RESEARCH_MAX_SEARCHES_PER_SUBAGENT})\n\n"
        f"## Search results so far\n\n{joined}\n\n"
        "Assess the results and reply with the required JSON."
    )

    try:
        with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
            response = await llm_service.call(
                [SystemMessage(content=_reflect_prompt()), HumanMessage(content=reflect_input)],
                model_name=settings.DEFAULT_LLM_MODEL,
                model_kwargs=_JSON_MODE,
            )
        decision = _parse_reflection_json(str(response.content) if response.content else "")
    except Exception as e:
        logger.warning("researcher_reflect_failed_stopping", error=str(e))
        return Command(goto="researcher_synthesize")

    note = decision.assessment or f"reflection round {rounds_done + 1}: {decision.status}"
    # Never let a follow-up batch push past the global per-sub-agent search cap.
    remaining = max(settings.RESEARCH_MAX_SEARCHES_PER_SUBAGENT - state.search_count, 0)
    next_searches = decision.next_searches[:remaining]

    if decision.status == "continue" and next_searches:
        logger.info(
            "researcher_reflect_continue",
            round=rounds_done + 1,
            next_searches=len(next_searches),
        )
        return Command(
            update={"reflection_notes": [note], "pending_searches": next_searches},
            goto="researcher_search",
        )

    logger.info("researcher_reflect_stop", round=rounds_done + 1, parsed_status=decision.status)
    return Command(update={"reflection_notes": [note]}, goto="researcher_synthesize")


async def _researcher_synthesize(state: ResearcherState) -> Command:
    """Write the sub-agent's findings from all accumulated search results."""
    joined = "\n\n---\n\n".join(state.search_results) if state.search_results else "No search results."
    messages = [
        SystemMessage(content=_subagent_prompt()),
        HumanMessage(
            content=(
                f"Research task: {state.task}\n\n"
                f"Search results:\n\n{joined}\n\n"
                "Produce your findings now in the required format."
            )
        ),
    ]

    with llm_inference_duration_seconds.labels(model=settings.DEFAULT_LLM_MODEL).time():
        response = await llm_service.call(messages, model_name=settings.DEFAULT_LLM_MODEL)

    raw = str(response.content).strip() if response.content else ""
    if not raw:
        logger.warning("researcher_synthesize_empty")
        raw = "No findings produced."

    logger.info("researcher_synthesize_done", findings_chars=len(raw), total_searches=state.search_count)
    return Command(update={"messages": [AIMessage(content=raw)]}, goto=END)


_compiled_graph: Optional[CompiledStateGraph] = None


def get_researcher_graph() -> CompiledStateGraph:
    """Return the compiled researcher sub-graph (built once on first access)."""
    global _compiled_graph
    if _compiled_graph is None:
        builder = StateGraph(ResearcherState)
        builder.add_node("researcher_plan", _researcher_plan, destinations=("researcher_search",))
        builder.add_node("researcher_search", _researcher_search, destinations=("researcher_reflect",))
        builder.add_node(
            "researcher_reflect",
            _researcher_reflect,
            destinations=("researcher_search", "researcher_synthesize"),
        )
        builder.add_node("researcher_synthesize", _researcher_synthesize, destinations=(END,))
        builder.set_entry_point("researcher_plan")
        builder.set_finish_point("researcher_synthesize")
        _compiled_graph = builder.compile(name="Researcher Sub-Agent")
        logger.info("researcher_graph_compiled")
    return _compiled_graph


async def run_researcher(task: str) -> str:
    """Run a single research task end-to-end and return the final findings text."""
    graph = get_researcher_graph()
    final_state = await graph.ainvoke({"task": task})

    messages = final_state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return "No findings produced."
