"""Registry that aggregates Skills and exposes them to the agent.

Discovery is explicit (``discover()``) rather than import-side-effect so the
order of imports stays predictable and tests can build a clean registry. Each
skill sub-package is expected to call ``SkillRegistry.register`` from its
``__init__.py`` as a side-effect of being imported.
"""

import importlib
import pkgutil
from typing import (
    ClassVar,
    Dict,
    List,
    Optional,
)

from langchain_core.tools.base import BaseTool

from app.core.config import settings
from app.core.langgraph.skills.base import (
    ADVANCED_TIER,
    CORE_TIER,
    Skill,
)
from app.core.logging import logger


class SkillRegistry:
    """Process-wide registry of all enabled skills.

    Use ``register`` from each skill's ``__init__.py`` and call ``discover``
    once at startup. ``collect_tools`` and ``render_usage_guide`` produce the
    payload consumed by the main agent.
    """

    _skills: ClassVar[Dict[str, Skill]] = {}
    _discovered: ClassVar[bool] = False
    _guide_cache: ClassVar[Optional[str]] = None

    @classmethod
    def register(cls, skill: Skill) -> None:
        """Register a skill, replacing any existing one with the same name."""
        if skill.name in cls._skills:
            logger.warning("skill_already_registered_replacing", skill_name=skill.name)
        cls._skills[skill.name] = skill
        cls._guide_cache = None  # invalidate
        logger.info(
            "skill_registered",
            skill_name=skill.name,
            tool_count=len(skill.tools),
            tools=[tool.name for tool in skill.tools],
        )

    @classmethod
    def get(cls, name: str) -> Skill:
        """Look up a registered skill by name."""
        return cls._skills[name]

    @classmethod
    def all(cls) -> List[Skill]:
        """Return the currently-enabled skills in registration order.

        Filters first by the ``SKILLS_ENABLED`` whitelist, then by the
        ``ENABLED_SKILLS_TIER`` setting (``"core"`` hides advanced skills).
        """
        enabled = cls._enabled_names()
        if enabled is None:
            skills = list(cls._skills.values())
        else:
            skills = [cls._skills[name] for name in enabled if name in cls._skills]

        tier = (getattr(settings, "ENABLED_SKILLS_TIER", "all") or "all").lower()
        if tier == CORE_TIER:
            skills = [s for s in skills if s.tier == CORE_TIER]
        elif tier not in {"all", ADVANCED_TIER}:
            logger.warning("invalid_enabled_skills_tier_falling_back_to_all", value=tier)
        return skills

    @classmethod
    def collect_tools(cls) -> List[BaseTool]:
        """Flatten all enabled skills' tools, de-duplicated by tool name.

        Order is preserved across (skill order, tool order). The first occurrence
        of a given tool name wins — later duplicates are silently skipped so a
        shared atomic tool can appear in multiple skills without confusing the LLM.
        """
        seen: Dict[str, BaseTool] = {}
        for skill in cls.all():
            for tool in skill.tools:
                if tool.name in seen:
                    continue
                seen[tool.name] = tool
        return list(seen.values())

    @classmethod
    def render_usage_guide(cls) -> str:
        """Render the markdown injected into the system prompt's tool_usage_guide slot.

        Cached after first call; invalidated whenever ``register`` or ``reset`` is
        called, so tests that rebuild the registry get a fresh guide.
        """
        if cls._guide_cache is not None:
            return cls._guide_cache
        skills = cls.all()
        if not skills:
            cls._guide_cache = "_No skills available._"
            return cls._guide_cache
        cls._guide_cache = "\n\n".join(skill.render_guide() for skill in skills)
        return cls._guide_cache

    @classmethod
    def discover(cls) -> None:
        """Import every sub-package under ``app.core.langgraph.skills`` exactly once.

        Each skill package is expected to call ``SkillRegistry.register`` as a
        side-effect of being imported. Failures in any single skill are logged
        but do not abort discovery — the rest of the agent still boots.
        """
        if cls._discovered:
            return
        package_name = "app.core.langgraph.skills"
        package = importlib.import_module(package_name)
        for module_info in pkgutil.iter_modules(package.__path__):
            if not module_info.ispkg:
                continue
            try:
                importlib.import_module(f"{package_name}.{module_info.name}")
            except Exception as e:
                logger.exception(
                    "skill_discovery_import_failed",
                    skill_module=module_info.name,
                    error=str(e),
                )
        cls._discovered = True
        logger.info(
            "skills_discovered",
            count=len(cls.all()),
            registered=list(cls._skills.keys()),
            enabled_filter=cls._enabled_names(),
        )

    @classmethod
    def reset(cls) -> None:
        """Clear all state — used in tests only."""
        cls._skills.clear()
        cls._discovered = False
        cls._guide_cache = None

    @classmethod
    def _enabled_names(cls) -> Optional[List[str]]:
        """Return the enabled-skills whitelist, or None when all skills are enabled."""
        raw = getattr(settings, "SKILLS_ENABLED", "")
        if not raw:
            return None
        return [name.strip() for name in raw.split(",") if name.strip()]
