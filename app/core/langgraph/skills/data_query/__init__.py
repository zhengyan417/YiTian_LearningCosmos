"""Data query skill — registers itself only when SQL DSN or HTTP whitelist is configured.

Keeping the registration conditional means the skill never appears in the LLM
tool set unless an operator has explicitly opted in by setting at least one of
``DATA_QUERY_READONLY_DSN`` / ``DATA_QUERY_ALLOWED_HOSTS``. Default = disabled.
"""

from app.core.config import settings
from app.core.langgraph.skills.data_query.skill import build_data_query_skill
from app.core.langgraph.skills.data_query.sql_tool import (
    shutdown,
    warm_up,
)
from app.core.langgraph.skills.registry import SkillRegistry
from app.core.logging import logger

if settings.DATA_QUERY_READONLY_DSN or settings.DATA_QUERY_ALLOWED_HOSTS:
    _skill = build_data_query_skill()
    SkillRegistry.register(_skill)
    logger.info(
        "data_query_skill_enabled",
        sql_enabled=bool(settings.DATA_QUERY_READONLY_DSN),
        http_enabled=bool(settings.DATA_QUERY_ALLOWED_HOSTS),
        host_count=len(settings.DATA_QUERY_ALLOWED_HOSTS),
        tools=[t.name for t in _skill.tools],
    )
else:
    logger.info("data_query_skill_disabled_no_config")

__all__ = ["warm_up", "shutdown"]
