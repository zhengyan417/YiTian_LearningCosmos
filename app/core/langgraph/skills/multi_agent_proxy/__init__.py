"""Multi-agent proxy skill — registers itself on import."""

from app.core.langgraph.skills.multi_agent_proxy.skill import multi_agent_proxy_skill
from app.core.langgraph.skills.registry import SkillRegistry

SkillRegistry.register(multi_agent_proxy_skill)

__all__ = ["multi_agent_proxy_skill"]
