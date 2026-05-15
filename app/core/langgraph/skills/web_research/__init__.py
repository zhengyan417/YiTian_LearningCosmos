"""Web research skill — registers itself on import."""

from app.core.langgraph.skills.registry import SkillRegistry
from app.core.langgraph.skills.web_research.skill import web_research_skill

SkillRegistry.register(web_research_skill)

__all__ = ["web_research_skill"]
