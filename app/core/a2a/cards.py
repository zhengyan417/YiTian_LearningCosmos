"""AgentCard definitions for the A2A specialist servers.

Each specialist publishes one AgentCard at
``{A2A_MOUNT_PREFIX}/{name}/.well-known/agent-card.json``; the coordinator's
A2A client resolves these cards to discover and call the specialists.
"""

from typing import Any

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
)

from app.core.config import settings

# Per-specialist metadata used to build AgentCards. Keyed by the specialist
# name, which also determines its mount path and is referenced by the coordinator.
_SPECIALIST_SPECS: dict[str, dict[str, Any]] = {
    "research": {
        "name": "Research Agent",
        "description": "Performs deep, multi-source research and returns a synthesized, cited report.",
        "skill": AgentSkill(
            id="deep_research",
            name="Deep Research",
            description=(
                "Decomposes a question into sub-tasks, runs concurrent web research sub-agents, "
                "and synthesizes a cited markdown report."
            ),
            tags=["research", "web", "report", "analysis"],
            examples=["Research the current state of solid-state battery commercialization"],
        ),
    },
    "search": {
        "name": "Search Agent",
        "description": "Runs a fast single web search and answers a narrow factual question.",
        "skill": AgentSkill(
            id="web_search",
            name="Web Search",
            description="Performs one web search and summarizes the results into a concise, cited answer.",
            tags=["search", "web", "facts"],
            examples=["What is the latest stable version of Python?"],
        ),
    },
    "writer": {
        "name": "Writer Agent",
        "description": "Summarizes, rewrites, reformats, or otherwise improves supplied text.",
        "skill": AgentSkill(
            id="writing",
            name="Writing & Editing",
            description="Transforms supplied text: summarize, rewrite, reformat, or improve it.",
            tags=["writing", "summarization", "editing"],
            examples=["Summarize this article into three bullet points"],
        ),
    },
    "coder": {
        "name": "Coder Agent",
        "description": "Answers programming questions, explains code, and writes code snippets.",
        "skill": AgentSkill(
            id="coding",
            name="Coding Assistant",
            description="Answers software and coding questions and produces working code with explanations.",
            tags=["coding", "programming", "software"],
            examples=["Write a Python function that debounces an async callable"],
        ),
    },
}

# The canonical specialist names, also used as mount-path segments.
SPECIALIST_NAMES: list[str] = list(_SPECIALIST_SPECS.keys())


def agent_base_url(name: str) -> str:
    """Return the externally reachable base URL for a specialist's A2A server.

    Args:
        name: The specialist name (research / search / writer / coder).

    Returns:
        The base URL, e.g. ``http://localhost:8000/a2a/research``.
    """
    base = settings.A2A_BASE_URL.rstrip("/")
    prefix = settings.A2A_MOUNT_PREFIX.strip("/")
    return f"{base}/{prefix}/{name}"


def build_agent_card(name: str) -> AgentCard:
    """Build the AgentCard advertised by one specialist's A2A server.

    Args:
        name: The specialist name (research / search / writer / coder).

    Returns:
        The AgentCard for that specialist.
    """
    spec = _SPECIALIST_SPECS[name]
    return AgentCard(
        name=spec["name"],
        description=spec["description"],
        url=f"{agent_base_url(name)}/",
        version=settings.VERSION,
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False),
        skills=[spec["skill"]],
    )
