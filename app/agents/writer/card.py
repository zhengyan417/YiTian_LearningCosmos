"""A2A AgentCard metadata for the writer agent."""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from app.core.config import settings

AGENT_NAME: str = "writer"


def build_card(base_url: str) -> AgentCard:
    """Build the AgentCard advertised by the writer A2A server."""
    return AgentCard(
        name="Writer Agent",
        description="Drafts new content from scratch or transforms supplied text (summarize, rewrite, reformat).",
        url=f"{base_url}/",
        version=settings.VERSION,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="writing",
                name="Writing & Editing",
                description="Drafts or transforms text: summarize, rewrite, reformat, or write from scratch.",
                tags=["writing", "summarization", "editing", "drafting"],
                examples=["Summarize this article into three bullet points"],
            ),
        ],
    )
