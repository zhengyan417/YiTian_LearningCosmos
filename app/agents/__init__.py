"""The five-agent multi-agent chat system.

Each subpackage (``coordinator`` / ``research`` / ``search`` / ``writer`` /
``coder``) is a self-contained LangGraph agent. The coordinator is the user-
facing entry point (mounted at ``POST /api/v1/chat``); the other four are
mounted as A2A specialist servers under ``settings.A2A_MOUNT_PREFIX`` so the
coordinator reaches them through the A2A protocol.

``AGENT_REGISTRY`` is populated lazily by ``_load_registry`` to keep imports
side-effect-free during partial-build / test scenarios.
"""

from app.agents.base import (
    Agent,
    AgentRunner,
)

# The subset of agents that should be exposed as A2A specialist servers. The
# coordinator is intentionally excluded — it's the A2A client, not a server.
SPECIALIST_NAMES: list[str] = ["research", "search", "writer", "coder"]


def _load_registry() -> dict[str, Agent]:
    """Build the agent registry on first call (avoids circular import).

    Importing each agent module here (rather than at module top) lets the
    coordinator and the A2A protocol layer import ``app.agents`` without
    forcing every agent to be importable simultaneously.
    """
    from app.agents.coder.agent import coder_agent
    from app.agents.coordinator.agent import coordinator_agent
    from app.agents.research.agent import research_agent
    from app.agents.search.agent import search_agent
    from app.agents.writer.agent import writer_agent

    return {
        "coordinator": coordinator_agent,
        "research": research_agent,
        "search": search_agent,
        "writer": writer_agent,
        "coder": coder_agent,
    }


_registry: dict[str, Agent] | None = None


def AGENT_REGISTRY() -> dict[str, Agent]:
    """Return the populated agent registry (caches on first call)."""
    global _registry
    if _registry is None:
        _registry = _load_registry()
    return _registry


__all__ = [
    "AGENT_REGISTRY",
    "SPECIALIST_NAMES",
    "Agent",
    "AgentRunner",
]
