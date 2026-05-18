"""A2A AgentCard metadata for the coder agent."""

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from app.core.config import settings

AGENT_NAME: str = "coder"


def build_card(base_url: str) -> AgentCard:
    """Build the AgentCard advertised by the coder A2A server."""
    return AgentCard(
        name="Coder Agent",
        description="Answers programming questions, explains code, and writes code snippets.",
        url=f"{base_url}/",
        version=settings.VERSION,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[
            AgentSkill(
                id="coding",
                name="Coding Assistant",
                description="Answers software and coding questions and produces working code with explanations.",
                tags=["coding", "programming", "software"],
                examples=["Write a Python function that debounces an async callable"],
            ),
        ],
    )
