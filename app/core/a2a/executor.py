"""A2A AgentExecutor adapter.

Bridges the A2A protocol surface (RequestContext / EventQueue / Task lifecycle)
to a plain ``async run(task, context_id) -> str`` specialist function. One
generic executor is parameterised per specialist; it holds no agent logic of
its own.
"""

from typing import override

from a2a.server.agent_execution import (
    AgentExecutor,
    RequestContext,
)
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    Part,
    TextPart,
)
from a2a.utils import new_task

from app.agents.base import AgentRunner
from app.core.logging import logger


class SpecialistAgentExecutor(AgentExecutor):
    """Generic A2A executor that delegates to a single specialist runner.

    The executor only translates between the A2A protocol and the specialist's
    uniform coroutine — all domain logic lives in the runner.
    """

    def __init__(self, name: str, runner: AgentRunner) -> None:
        """Initialize the executor for one specialist.

        Args:
            name: The specialist's name (research / search / writer / coder).
            runner: The specialist's ``async (task, context_id) -> str`` coroutine.
        """
        self._name = name
        self._runner = runner

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Run the specialist for an incoming A2A request and emit task events.

        Args:
            context: The A2A request context carrying the user message and task.
            event_queue: The queue used to publish task lifecycle events.

        Raises:
            ValueError: When the request carries neither a current task nor a message.
        """
        user_input = context.get_user_input()
        task = context.current_task
        if task is None:
            if context.message is None:
                raise ValueError("a2a request has neither a current task nor a message")
            task = new_task(context.message)
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        logger.info(
            "a2a_executor_start",
            agent=self._name,
            task_id=task.id,
            context_id=task.context_id,
        )
        await updater.start_work()

        try:
            result = await self._runner(user_input, task.context_id)
            await updater.add_artifact(
                [Part(root=TextPart(text=result))],
                name=f"{self._name}_result",
            )
            await updater.complete()
            logger.info("a2a_executor_complete", agent=self._name, task_id=task.id)
        except Exception as e:
            logger.exception("a2a_executor_failed", agent=self._name, task_id=task.id, error=str(e))
            await updater.failed(
                updater.new_agent_message([Part(root=TextPart(text=f"{self._name} agent failed: {e}"))])
            )

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Reject cancellation — the stateless specialist agents run to completion.

        Args:
            context: The A2A request context.
            event_queue: The task event queue.

        Raises:
            NotImplementedError: Always — cancellation is unsupported.
        """
        logger.warning("a2a_executor_cancel_unsupported", agent=self._name)
        raise NotImplementedError("specialist agents do not support cancellation")
