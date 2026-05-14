"""Builds and mounts the A2A specialist servers onto the FastAPI application.

Each specialist becomes its own A2A server (AgentCard + AgentExecutor +
DefaultRequestHandler) and is mounted as a sub-application under
``settings.A2A_MOUNT_PREFIX``. The coordinator reaches them as an A2A client.
"""

from a2a.server.apps import A2AFastAPIApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from fastapi import FastAPI

from app.core.a2a.cards import (
    SPECIALIST_NAMES,
    build_agent_card,
)
from app.core.a2a.executor import SpecialistAgentExecutor
from app.core.a2a.specialists import SPECIALIST_RUNNERS
from app.core.config import settings
from app.core.logging import logger


def mount_a2a_servers(app: FastAPI) -> None:
    """Mount every specialist's A2A server as a sub-application of ``app``.

    Each specialist gets an independent in-memory task store and JSON-RPC A2A
    server mounted at ``{A2A_MOUNT_PREFIX}/{name}``.

    Args:
        app: The main FastAPI application to mount the A2A servers onto.
    """
    if not settings.A2A_ENABLED:
        logger.info("a2a_servers_disabled")
        return

    prefix = settings.A2A_MOUNT_PREFIX.rstrip("/")
    for name in SPECIALIST_NAMES:
        handler = DefaultRequestHandler(
            agent_executor=SpecialistAgentExecutor(name, SPECIALIST_RUNNERS[name]),
            task_store=InMemoryTaskStore(),
        )
        a2a_app = A2AFastAPIApplication(agent_card=build_agent_card(name), http_handler=handler)
        app.mount(f"{prefix}/{name}", a2a_app.build())
        logger.info("a2a_server_mounted", agent=name, path=f"{prefix}/{name}")

    logger.info("a2a_servers_mounted", count=len(SPECIALIST_NAMES), prefix=prefix)
