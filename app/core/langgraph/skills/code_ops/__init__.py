"""Code ops skill — registers itself only when the sandbox is configured.

Skipping registration when ``CODE_OPS_ALLOWED_ROOTS`` is empty avoids exposing
the LLM to a tool that would always answer "outside the sandbox" — an empty
configuration is the operator's signal that filesystem access is disabled in
this environment.
"""

from app.core.langgraph.skills.code_ops.safety import get_allowed_roots
from app.core.langgraph.skills.code_ops.skill import code_ops_skill
from app.core.langgraph.skills.registry import SkillRegistry
from app.core.logging import logger

_roots = get_allowed_roots()
if _roots:
    SkillRegistry.register(code_ops_skill)
    logger.info("code_ops_skill_enabled", root_count=len(_roots), roots=[str(r) for r in _roots])
else:
    logger.info("code_ops_skill_disabled_no_roots_configured")

__all__ = ["code_ops_skill"]
