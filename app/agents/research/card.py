"""A2A AgentCard metadata for the research agent."""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from app.core.config import settings

AGENT_NAME: str = "research"


def build_card(base_url: str) -> AgentCard:
    """Build the AgentCard advertised by the research A2A server.

    Args:
        base_url: Externally reachable base URL of this agent's A2A server.

    Returns:
        The configured AgentCard.
    """
    return AgentCard(
        name="Research Agent",
        description="Performs deep, multi-source research and returns a synthesized, cited report.",
        url=f"{base_url}/",
        version=settings.VERSION,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="deep_research",
                name="Deep Research",
                description=(
                    "Decomposes a question into sub-tasks, runs concurrent web research sub-agents, "
                    "and synthesizes a cited markdown report."
                ),
                tags=["research", "web", "report", "analysis"],
                examples=["Research the current state of solid-state battery commercialization"],
            ),
        ],
    )
