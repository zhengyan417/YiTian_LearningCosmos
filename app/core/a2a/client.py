"""A2A client used by the coordinator to call the specialist servers.

Holds one shared httpx client, resolves each specialist's AgentCard, sends it a
task over the A2A protocol, and returns the specialist's final result text.
"""

from typing import Optional

import httpx
from a2a.client import (
    A2ACardResolver,
    ClientConfig,
    ClientFactory,
    create_text_message_object,
)
from a2a.types import (
    Role,
    Task,
    TransportProtocol,
)
from a2a.utils import (
    get_artifact_text,
    get_message_text,
)

from app.core.config import settings
from app.core.logging import logger


def agent_base_url(name: str) -> str:
    """Return the externally reachable base URL of a specialist's A2A server.

    Inlined here (rather than imported) so the client stays decoupled from any
    individual agent package — it speaks only the A2A protocol.

    Args:
        name: The specialist name (research / search / writer / coder).

    Returns:
        The base URL, e.g. ``http://localhost:8000/a2a/research``.
    """
    base = settings.A2A_BASE_URL.rstrip("/")
    prefix = settings.A2A_MOUNT_PREFIX.strip("/")
    return f"{base}/{prefix}/{name}"


def _extract_task_text(task: Task) -> str:
    """Pull the result text out of a terminal A2A task.

    Prefers task artifacts; falls back to the final status message.

    Args:
        task: The terminal A2A task returned by a specialist.

    Returns:
        The concatenated result text, or an empty string when none is present.
    """
    chunks: list[str] = []
    if task.artifacts:
        for artifact in task.artifacts:
            text = get_artifact_text(artifact)
            if text:
                chunks.append(text)
    if chunks:
        return "\n\n".join(chunks)
    if task.status and task.status.message:
        return get_message_text(task.status.message)
    return ""


class A2ASpecialistClient:
    """A2A client wrapper that resolves and calls the specialist servers."""

    def __init__(self) -> None:
        """Initialize the client with a deferred (lazily created) httpx client."""
        self._httpx: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        """Create the shared httpx client if it does not exist yet."""
        if self._httpx is None:
            self._httpx = httpx.AsyncClient(timeout=settings.A2A_CLIENT_TIMEOUT)
            logger.info("a2a_specialist_client_initialized", timeout=settings.A2A_CLIENT_TIMEOUT)

    async def close(self) -> None:
        """Close the shared httpx client."""
        if self._httpx is not None:
            await self._httpx.aclose()
            self._httpx = None
            logger.info("a2a_specialist_client_closed")

    async def call(self, agent_name: str, prompt: str, context_id: str) -> str:
        """Send a task to a specialist's A2A server and return its final text.

        Args:
            agent_name: The specialist to call (research / search / writer / coder).
            prompt: The task description for the specialist.
            context_id: A2A context id correlating this call to the user request.

        Returns:
            The specialist's final result text.

        Raises:
            RuntimeError: When the client has not been initialized.
        """
        if self._httpx is None:
            raise RuntimeError("a2a specialist client not initialized")

        resolver = A2ACardResolver(httpx_client=self._httpx, base_url=agent_base_url(agent_name))
        card = await resolver.get_agent_card()

        config = ClientConfig(
            httpx_client=self._httpx,
            streaming=False,
            supported_transports=[TransportProtocol.jsonrpc],
        )
        client = ClientFactory(config).create(card)

        message = create_text_message_object(role=Role.user, content=prompt)
        message.context_id = context_id

        logger.info("a2a_specialist_call_start", agent=agent_name, context_id=context_id)
        result_text = ""
        async for event in client.send_message(message):
            if isinstance(event, tuple):
                task, _update = event
                result_text = _extract_task_text(task)
            else:
                result_text = get_message_text(event)

        logger.info(
            "a2a_specialist_call_complete",
            agent=agent_name,
            context_id=context_id,
            result_chars=len(result_text),
        )
        return result_text or "No response from agent."


# Module-level singleton — initialized and closed by the FastAPI lifespan.
a2a_specialist_client = A2ASpecialistClient()
