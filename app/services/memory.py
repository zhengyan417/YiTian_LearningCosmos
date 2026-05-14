"""Long-term memory service using mem0ai with DashScope text-embedding-v4 + DeepSeek LLM."""

import inspect

from mem0 import AsyncMemory

from app.core.cache import cache_key, cache_service
from app.core.config import settings
from app.core.logging import logger


class MemoryService:
    """Service for managing long-term memory using mem0ai and pgvector."""

    def __init__(self) -> None:
        """Initialize the memory service with lazy mem0ai client."""
        self._memory: AsyncMemory | None = None

    async def _get_memory(self) -> AsyncMemory:
        if self._memory is None:
            result = AsyncMemory.from_config(
                config_dict={
                    "vector_store": {
                        "provider": "pgvector",
                        "config": {
                            "collection_name": settings.LONG_TERM_MEMORY_COLLECTION_NAME,
                            "dbname": settings.POSTGRES_DB,
                            "user": settings.POSTGRES_USER,
                            "password": settings.POSTGRES_PASSWORD,
                            "host": settings.POSTGRES_HOST,
                            "port": settings.POSTGRES_PORT,
                        },
                    },
                    "llm": {
                        "provider": "deepseek",
                        "config": {
                            "model": settings.LONG_TERM_MEMORY_MODEL,
                            "api_key": settings.OPENAI_API_KEY,
                            "deepseek_base_url": settings.LLM_BASE_URL,
                        },
                    },
                    "embedder": {
                        "provider": "openai",
                        "config": {
                            "model": settings.LONG_TERM_MEMORY_EMBEDDER_MODEL,
                            "api_key": settings.DASHSCOPE_API_KEY,
                            "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                            "embedding_dims": 1024,
                        },
                    },
                }
            )
            # mem0ai changed from_config between sync/async across versions.
            # Detect at runtime so we work with either.
            if inspect.iscoroutine(result):
                self._memory = await result
            else:
                self._memory = result
        return self._memory

    async def initialize(self) -> None:
        """Pre-warm the mem0ai AsyncMemory instance and its pgvector connection pool."""
        try:
            await self._get_memory()
            logger.info("memory_service_initialized")
        except Exception as e:
            logger.exception("memory_service_initialization_failed", error=str(e))

    async def search(self, user_id: str | None, query: str) -> str:
        """Search relevant memories for a user.

        Checks cache first; on miss, queries mem0ai and caches the result.
        """
        if user_id is None:
            return ""
        try:
            key = cache_key("memory", str(user_id), query)
            cached = await cache_service.get(key)
            if cached is not None:
                logger.debug("memory_search_cache_hit", user_id=user_id)
                return cached

            memory = await self._get_memory()
            results = await memory.search(user_id=str(user_id), query=query)
            result = "\n".join([f"* {r['memory']}" for r in results["results"]])

            if result:
                await cache_service.set(key, result)

            return result
        except Exception as e:
            logger.error("failed_to_get_relevant_memory", error=str(e), user_id=user_id, query=query)
            return ""

    async def add(self, user_id: str | None, messages: list[dict], metadata: dict | None = None) -> None:
        """Add messages to long-term memory for a user."""
        if user_id is None:
            return
        try:
            memory = await self._get_memory()
            await memory.add(messages, user_id=str(user_id), metadata=metadata)
            logger.info("long_term_memory_updated_successfully", user_id=user_id)
        except Exception as e:
            logger.exception("failed_to_update_long_term_memory", user_id=user_id, error=str(e))


memory_service = MemoryService()
