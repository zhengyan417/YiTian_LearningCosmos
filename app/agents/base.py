"""Shared protocol and helpers for all agents.

Every agent in ``app.agents`` exposes a uniform ``run(task, context_id) -> str``
coroutine so the A2A executor can treat them identically. Each agent owns its
own LangGraph internally and decides whether it needs checkpointing, sub-agents,
or external tools.
"""

import os
from collections.abc import (
    Awaitable,
    Callable,
)
from datetime import datetime
from typing import (
    Any,
    Protocol,
)

# The signature every agent's ``run`` method satisfies. The A2A executor and
# the coordinator's dispatch loop both treat agents through this type.
AgentRunner = Callable[[str, str], Awaitable[str]]


class Agent(Protocol):
    """Structural protocol every concrete agent satisfies.

    Implementations live in ``app.agents.<name>.agent`` and are exposed via
    ``app.agents.AGENT_REGISTRY``.
    """

    async def run(self, task: str, context_id: str) -> str:
        """Execute the agent's workflow for one task.

        Args:
            task: The natural-language task description.
            context_id: A correlation id (usually the A2A context id) for
                logging and per-request resource keys (e.g. checkpoint thread).

        Returns:
            The agent's final answer as plain markdown text.
        """
        ...

    def create_graph(self) -> Any:
        """Compile (and cache) the agent's LangGraph.

        Called once during application startup to pre-warm graphs and to give
        each agent a chance to open any connection pools it owns. The return
        type is ``Any`` because concrete implementations return either the
        compiled graph directly (sync) or an awaitable that resolves to it
        (async, used by the research agent which opens a PostgreSQL pool).
        Startup code in ``app.main.lifespan`` handles both shapes.
        """
        ...


def now_str() -> str:
    """Return the current local time in ``YYYY-MM-DD HH:MM:SS`` format.

    Centralized so every agent prompt-loader formats time consistently.
    """
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_prompt(package_file: str, name: str) -> str:
    """Read a prompt file from an agent's ``prompts/`` subdirectory.

    Args:
        package_file: Pass ``__file__`` of the calling agent module so the
            lookup is relative to that agent's package.
        name: The prompt file name (e.g. ``"router.md"``).

    Returns:
        The raw prompt template contents.
    """
    prompts_dir = os.path.join(os.path.dirname(package_file), "prompts")
    with open(os.path.join(prompts_dir, name), "r", encoding="utf-8") as f:
        return f.read()
