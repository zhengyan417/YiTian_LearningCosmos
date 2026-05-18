"""Placeholder AgentCard for the coordinator (not mounted as an A2A server).

The coordinator is the A2A *client* — it calls the four specialist servers via
``a2a_specialist_client`` and is itself reached by users via the regular
``POST /api/v1/chat`` route, not the A2A protocol. The card here exists only to
keep the per-agent folder layout uniform and to document the agent for any
future tooling that surveys ``app.agents``.
"""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from app.core.config import settings

AGENT_NAME: str = "coordinator"


def build_card(base_url: str) -> AgentCard:
    """Build the descriptive AgentCard for the coordinator.

    The coordinator is not actually mounted as an A2A server, so this card is
    not consumed by ``app.core.a2a.server`` — it exists for documentation only.
    """
    return AgentCard(
        name="Coordinator Agent",
        description=(
            "Routes a user request to the appropriate specialist agents (research / search / "
            "writer / coder) over A2A, then synthesizes their results into one final answer."
        ),
        url=f"{base_url}/",
        version=settings.VERSION,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="multi_agent_chat",
                name="Multi-Agent Chat",
                description="Plans, delegates, and integrates across the four specialist agents.",
                tags=["coordination", "multi-agent", "planning"],
                examples=["Research X, write a summary, and draft code for it"],
            ),
        ],
    )
