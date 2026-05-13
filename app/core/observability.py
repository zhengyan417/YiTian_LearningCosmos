"""Observability module for the application."""

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import logger

if TYPE_CHECKING:
    pass


def langfuse_init():
    """Initialize Langfuse."""
    if not settings.LANGFUSE_TRACING_ENABLED:
        logger.debug("langfuse_tracing_disabled")
        return

    from langfuse import Langfuse

    langfuse = Langfuse(
        tracing_enabled=settings.LANGFUSE_TRACING_ENABLED,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        secret_key=settings.LANGFUSE_SECRET_KEY,
        host=settings.LANGFUSE_HOST,
        environment=settings.ENVIRONMENT.value,
        debug=settings.DEBUG,
    )

    if langfuse.auth_check():
        logger.debug("langfuse_auth_success")
    else:
        logger.debug("langfuse_auth_failure")


_langfuse_handler = None


def get_langfuse_callback_handler():
    """Create a Langfuse CallbackHandler for tracking LLM interactions.

    Only initializes when tracing is enabled.
    """
    global _langfuse_handler
    if _langfuse_handler is None and settings.LANGFUSE_TRACING_ENABLED:
        from langfuse.langchain import CallbackHandler

        _langfuse_handler = CallbackHandler()
    return _langfuse_handler
