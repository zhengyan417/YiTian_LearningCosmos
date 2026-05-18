"""Builds and mounts the A2A specialist servers onto the FastAPI application.

For each specialist name in ``app.agents.SPECIALIST_NAMES`` we wire together:

- the agent's ``run`` coroutine (from ``app.agents.AGENT_REGISTRY``),
- an ``AgentCard`` (from that agent's ``card.build_card``),
- a ``SpecialistAgentExecutor`` (the generic A2A adapter),

and mount the resulting A2A application under ``{A2A_MOUNT_PREFIX}/{name}``.
The coordinator reaches each specialist through ``a2a_specialist_client``.
"""

import importlib

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from fastapi import FastAPI

from app.agents import (
    AGENT_REGISTRY,
    SPECIALIST_NAMES,
)
from app.core.a2a.executor import SpecialistAgentExecutor
from app.core.config import settings
from app.core.logging import logger


def _agent_base_url(name: str) -> str:
    """Return the externally reachable base URL of a specialist's A2A server."""
    base = settings.A2A_BASE_URL.rstrip("/")
    prefix = settings.A2A_MOUNT_PREFIX.strip("/")
    return f"{base}/{prefix}/{name}"


def _load_card(name: str) -> AgentCard:
    """Import ``app.agents.<name>.card.build_card`` and call it with the URL."""
    module = importlib.import_module(f"app.agents.{name}.card")
    return module.build_card(_agent_base_url(name))


def mount_a2a_servers(app: FastAPI) -> None:
    """Mount every specialist's A2A server as a sub-application of ``app``.

    Args:
        app: The main FastAPI application to mount the A2A sub-applications onto.
    """
    if not settings.A2A_ENABLED:
        logger.info("a2a_servers_disabled")
        return

    registry = AGENT_REGISTRY()
    prefix = settings.A2A_MOUNT_PREFIX.rstrip("/")
    for name in SPECIALIST_NAMES:
        agent = registry[name]
        handler = DefaultRequestHandler(
            agent_executor=SpecialistAgentExecutor(name, agent.run),
            task_store=InMemoryTaskStore(),
        )
        a2a_app = A2AFastAPIApplication(agent_card=_load_card(name), http_handler=handler)
        app.mount(f"{prefix}/{name}", a2a_app.build())
        logger.info("a2a_server_mounted", agent=name, path=f"{prefix}/{name}")

    logger.info("a2a_servers_mounted", count=len(SPECIALIST_NAMES), prefix=prefix)
