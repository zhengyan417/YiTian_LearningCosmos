"""Interactive skill — registers itself on import."""

from app.core.langgraph.skills.interactive.skill import interactive_skill
from app.core.langgraph.skills.registry import SkillRegistry

SkillRegistry.register(interactive_skill)

__all__ = ["interactive_skill"]
