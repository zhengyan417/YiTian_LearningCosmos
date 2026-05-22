"""State and structured output schemas for the deep research workflow."""

import operator
from typing import Annotated

from langgraph.graph.message import add_messages
from pydantic import (
    BaseModel,
    Field,
)


class ResearchPlan(BaseModel):
    """Structured output for the planner node.

    Captures the orchestrator's decomposition of a user request into focused
    sub-tasks. Each task will be handed to one researcher sub-agent.
    """

    tasks: list[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="Focused, self-contained research sub-tasks (1 per sub-agent)",
    )


class ResearchFinding(BaseModel):
    """One researcher sub-agent's result, paired with the task that produced it.

    The orchestrator accumulates these across supervisor rounds so both the
    supervisor and the synthesizer can see which task each finding answers.
    """

    task: str = Field(..., description="The research task handed to the sub-agent")
    content: str = Field(..., description="The sub-agent's findings text")


class SupervisorDecision(BaseModel):
    """Parsed supervisor response. Defaults bias toward completing research."""

    decision: str = Field(default="complete")
    reasoning: str = Field(default="")
    new_tasks: list[str] = Field(default_factory=list)


class DeepResearchState(BaseModel):
    """State definition for the main orchestrator graph.

    The orchestrator runs ``plan → dispatch ⇄ supervise → synthesize``. The
    ``dispatch`` node can be re-entered across supervisor rounds, so the fields
    it accumulates into (``findings``, ``completed_tasks``) carry an
    ``operator.add`` reducer. ``research_tasks`` is *replaced* each round (it is
    the current round's queue) and therefore has no reducer.
    """

    messages: Annotated[list, add_messages] = Field(
        default_factory=list,
        description="Conversation messages, primarily the user request and final report",
    )
    research_request: str = Field(default="", description="The original research request")
    research_tasks: list[str] = Field(default_factory=list, description="The current round's pending sub-tasks")
    findings: Annotated[list[ResearchFinding], operator.add] = Field(
        default_factory=list,
        description="Findings from every sub-agent, accumulated across supervisor rounds",
    )
    completed_tasks: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="Every research task dispatched so far, across all rounds",
    )
    supervisor_notes: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="The supervisor's per-round reasoning trail",
    )
    supervisor_rounds: int = Field(default=0, description="Number of completed supervisor follow-up rounds")
    final_report: str = Field(default="", description="Synthesized final markdown report")


class ResearcherState(BaseModel):
    """State definition for a single researcher sub-graph invocation.

    The sub-graph runs ``plan → search ⇄ reflect → synthesize``. ``search`` is
    re-entered whenever ``reflect`` queues follow-up searches, so ``search_results``
    and ``reflection_notes`` carry ``operator.add`` reducers. ``pending_searches``
    is *replaced* each round (the current round's queue) and has no reducer.
    """

    messages: Annotated[list, add_messages] = Field(
        default_factory=list,
        description="Sub-agent conversation, primarily the final findings message",
    )
    task: str = Field(default="", description="The specific research task assigned to this sub-agent")
    search_count: int = Field(default=0, description="Running total of tavily_search calls executed")
    pending_searches: list[str] = Field(default_factory=list, description="The current round's queued searches")
    search_results: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="Raw search results, accumulated across reflection rounds",
    )
    reflection_notes: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="The reflect node's per-round assessment; its length doubles as the round counter",
    )
