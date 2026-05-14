"""Request, response, and routing schemas for the A2A multi-agent coordinator."""

import re
from typing import (
    Literal,
    Optional,
)

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)

from app.schemas.base import BaseResponse

# The set of specialist agents the coordinator can delegate to. Each name maps
# to an A2A server mounted under settings.A2A_MOUNT_PREFIX.
SpecialistName = Literal["research", "search", "writer", "coder"]


class MultiAgentRequest(BaseModel):
    """Request model for the multi-agent coordinator endpoint.

    Attributes:
        query: The user's request for the multi-agent system to handle.
    """

    query: str = Field(
        ...,
        min_length=3,
        max_length=3000,
        description="The user's request for the multi-agent system",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Reject obviously dangerous payloads (script tags, null bytes)."""
        if re.search(r"<script.*?>.*?</script>", v, re.IGNORECASE | re.DOTALL):
            raise ValueError("query contains potentially harmful script tags")
        if "\0" in v:
            raise ValueError("query contains null bytes")
        return v


class Delegation(BaseModel):
    """A single unit of work the coordinator routes to one specialist agent.

    Attributes:
        agent: The specialist that should handle this delegation.
        task: A precise, self-contained task description for that specialist.
    """

    agent: SpecialistName = Field(..., description="The specialist agent to delegate to")
    task: str = Field(..., description="A precise, self-contained task for the specialist")


class RoutingDecision(BaseModel):
    """Structured output schema for the coordinator's routing LLM call.

    Attributes:
        reasoning: Short explanation of why the request was routed this way.
        direct_answer: A direct reply when no specialist is needed; ``None`` otherwise.
        delegations: The specialists to invoke; empty when ``direct_answer`` is set.
    """

    reasoning: str = Field(..., description="Brief explanation of the routing decision")
    direct_answer: Optional[str] = Field(
        default=None,
        description="A direct reply to the user when no specialist delegation is needed",
    )
    delegations: list[Delegation] = Field(
        default_factory=list,
        description="Specialist delegations to run; empty when direct_answer is set",
    )


class AgentResult(BaseModel):
    """The outcome of one specialist delegation.

    Attributes:
        agent: The specialist that produced this result.
        task: The task the specialist was given.
        output: The specialist's returned text.
    """

    agent: str = Field(..., description="The specialist agent that produced the result")
    task: str = Field(..., description="The task the specialist was given")
    output: str = Field(..., description="The specialist's returned text")


class MultiAgentResponse(BaseResponse):
    """Response model for the multi-agent coordinator endpoint.

    Attributes:
        answer: The final synthesized answer for the user.
        routing_reasoning: The coordinator's explanation of how it routed the request.
        delegations: Per-specialist results that fed into the final answer.
    """

    answer: str = Field(..., description="The final synthesized answer for the user")
    routing_reasoning: str = Field(default="", description="How the coordinator routed the request")
    delegations: list[AgentResult] = Field(
        default_factory=list,
        description="Per-specialist results that fed into the final answer",
    )
