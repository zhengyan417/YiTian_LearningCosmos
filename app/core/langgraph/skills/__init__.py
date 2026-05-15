"""Skill abstraction layer for the main LangGraph agent.

A skill bundles a set of related tools with selection metadata. The metadata is
rendered into the system prompt so the LLM knows which skill to invoke for a
given turn.

See:
    - ``app.core.langgraph.skills.base.Skill`` for the data model.
    - ``app.core.langgraph.skills.registry.SkillRegistry`` for the registry.

Each sub-package under this one is a single skill and is expected to call
``SkillRegistry.register`` from its ``__init__.py`` when imported.
"""

from app.core.langgraph.skills.base import Skill
from app.core.langgraph.skills.registry import SkillRegistry

__all__ = ["Skill", "SkillRegistry"]
