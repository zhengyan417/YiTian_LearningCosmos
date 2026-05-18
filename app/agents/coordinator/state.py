"""State schema for the coordinator agent's LangGraph workflow."""

from typing import Optional

from pydantic import (
    BaseModel,
    Field,
)

from app.schemas.multi_agent import (
    AgentResult,
    Delegation,
)


class CoordinatorState(BaseModel):
    """State for the coordinator's route -> dispatch -> synthesize graph.

    Attributes:
        query: The original user request.
        context_id: A2A context id correlating all specialist calls.

        routing_reasoning: The route node's explanation of its decision.
        direct_answer: A direct reply when no specialist is needed. When set,
            dispatch and synthesize are skipped.
        delegations: Specialist delegations chosen by the route node.

        results: One AgentResult per delegation; populated by dispatch.

        answer: Final answer text for the user; populated by synthesize.
    """

    query: str = Field(default="", description="The original user request")
    context_id: str = Field(default="", description="A2A context id")

    routing_reasoning: str = Field(default="", description="Why the request was routed this way")
    direct_answer: Optional[str] = Field(
        default=None,
        description="Direct reply when no specialist is needed; ``None`` triggers dispatch",
    )
    delegations: list[Delegation] = Field(default_factory=list, description="Planned specialist delegations")

    results: list[AgentResult] = Field(default_factory=list, description="Per-specialist results from dispatch")

    answer: str = Field(default="", description="Final answer text returned to the user")
