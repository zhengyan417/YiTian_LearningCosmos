"""Skill abstraction over LangChain tools.

A Skill bundles 1..N related tools with metadata describing when the LLM
should — and should NOT — invoke them. The metadata is rendered into the
system prompt so the agent picks the right skill for a given turn.
"""

from dataclasses import dataclass
from typing import List

from langchain_core.tools.base import BaseTool


CORE_TIER = "core"
ADVANCED_TIER = "advanced"
ALLOWED_TIERS = frozenset({CORE_TIER, ADVANCED_TIER})


@dataclass(frozen=True)
class Skill:
    """A bundle of related tools plus selection metadata.

    The ``tools`` are bound to the LLM exactly as today; the metadata
    fields (``when_to_use`` / ``when_not_to_use`` / ``examples``) are
    rendered by ``SkillRegistry.render_usage_guide`` and injected into
    the system prompt under ``{tool_usage_guide}``.

    ``tier`` controls when the skill is exposed:
        - ``"core"``: always exposed (default; cheap or essential).
        - ``"advanced"``: exposed only when ``ENABLED_SKILLS_TIER`` is ``"all"``;
          use this for heavy / proxy skills that should not crowd the prompt
          when a leaner agent is desired.
    """

    name: str
    summary: str
    when_to_use: str
    when_not_to_use: str
    examples: List[str]
    tools: List[BaseTool]
    tier: str = CORE_TIER

    def __post_init__(self) -> None:
        """Validate tier so a typo can't silently exclude a skill."""
        if self.tier not in ALLOWED_TIERS:
            raise ValueError(f"Skill '{self.name}' has invalid tier '{self.tier}'. Allowed: {sorted(ALLOWED_TIERS)}.")

    def render_guide(self) -> str:
        """Render this skill as a markdown section for the system prompt."""
        tool_names = ", ".join(f"`{tool.name}`" for tool in self.tools) or "_(no tools)_"
        examples_md = "\n".join(f"- {example}" for example in self.examples) if self.examples else "_(no examples)_"
        return (
            f"## {self.name} — {self.summary}\n"
            f"**When to use**: {self.when_to_use}\n"
            f"**When NOT to use**: {self.when_not_to_use}\n"
            f"**Tools**: {tool_names}\n"
            f"**Examples**:\n{examples_md}\n"
        )
