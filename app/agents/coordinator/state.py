"""State schema for the coordinator agent's LangGraph workflow."""

import operator
from typing import (
    Annotated,
    Optional,
)

from pydantic import (
    BaseModel,
    Field,
)

from app.schemas.multi_agent import (
    AgentResult,
    Delegation,
)


class CoordinatorState(BaseModel):
    """State for the coordinator's ``route → dispatch ⇄ reflect → synthesize`` graph.

    The ``dispatch`` node can be re-entered across reflection rounds, so
    ``results`` carries an ``operator.add`` reducer and accumulates every
    round's specialist results. ``delegations`` is *replaced* each round (it is
    the current round's queue) and therefore has no reducer.

    Attributes:
        query: The original user request.
        context_id: A2A context id correlating all specialist calls.

        routing_reasoning: The route node's explanation of its decision.
        direct_answer: A direct reply when no specialist is needed. When set,
            dispatch, reflect and synthesize are skipped.
        delegations: The current round's specialist delegations — set by the
            route node, replaced by the reflect node on each follow-up round.

        results: One AgentResult per delegation, accumulated across all
            reflection rounds.
        reflection_rounds: Number of completed reflection follow-up rounds.
        reflection_notes: The reflect node's per-round reasoning trail.

        answer: Final answer text for the user; populated by synthesize.
    """

    query: str = Field(default="", description="The original user request")
    context_id: str = Field(default="", description="A2A context id")

    routing_reasoning: str = Field(default="", description="Why the request was routed this way")
    direct_answer: Optional[str] = Field(
        default=None,
        description="Direct reply when no specialist is needed; ``None`` triggers dispatch",
    )
    delegations: list[Delegation] = Field(
        default_factory=list,
        description="The current round's planned specialist delegations",
    )

    results: Annotated[list[AgentResult], operator.add] = Field(
        default_factory=list,
        description="Per-specialist results, accumulated across reflection rounds",
    )
    reflection_rounds: int = Field(default=0, description="Number of completed reflection follow-up rounds")
    reflection_notes: Annotated[list[str], operator.add] = Field(
        default_factory=list,
        description="The reflect node's per-round reasoning trail",
    )

    answer: str = Field(default="", description="Final answer text returned to the user")
