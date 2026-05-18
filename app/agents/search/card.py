"""A2A AgentCard metadata for the search agent."""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from app.core.config import settings

AGENT_NAME: str = "search"


def build_card(base_url: str) -> AgentCard:
    """Build the AgentCard advertised by the search A2A server."""
    return AgentCard(
        name="Search Agent",
        description="Runs a fast single web search and answers a narrow factual question.",
        url=f"{base_url}/",
        version=settings.VERSION,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="web_search",
                name="Web Search",
                description="Performs one web search and summarizes the results into a concise, cited answer.",
                tags=["search", "web", "facts"],
                examples=["What is the latest stable version of Python?"],
            ),
        ],
    )
