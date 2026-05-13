"""State and structured output schemas for the deep research workflow."""

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


class DeepResearchState(BaseModel):
    """State definition for the main orchestrator graph."""

    messages: Annotated[list, add_messages] = Field(
        default_factory=list,
        description="Conversation messages, primarily the user request and final report",
    )
    research_request: str = Field(default="", description="The original research request")
    research_tasks: list[str] = Field(default_factory=list, description="Planned sub-tasks")
    findings: list[str] = Field(default_factory=list, description="Raw findings from each sub-agent")
    final_report: str = Field(default="", description="Synthesized final markdown report")


class ResearcherState(BaseModel):
    """State definition for a single researcher sub-graph invocation."""

    messages: Annotated[list, add_messages] = Field(
        default_factory=list,
        description="Sub-agent conversation including tool calls",
    )
    task: str = Field(default="", description="The specific research task assigned to this sub-agent")
    search_count: int = Field(default=0, description="Number of tavily_search calls executed so far")
    pending_searches: list[str] = Field(default_factory=list, description="Searches queued by the planner")
    search_results: list[str] = Field(default_factory=list, description="Raw results from executed searches")
