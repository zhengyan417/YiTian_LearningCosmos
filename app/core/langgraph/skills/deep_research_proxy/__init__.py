"""Deep research proxy skill — registers itself on import."""

from app.core.langgraph.skills.deep_research_proxy.proxy_tool import (
    shutdown,
    warm_up,
)
from app.core.langgraph.skills.deep_research_proxy.skill import deep_research_proxy_skill
from app.core.langgraph.skills.registry import SkillRegistry

SkillRegistry.register(deep_research_proxy_skill)

__all__ = ["deep_research_proxy_skill", "warm_up", "shutdown"]
