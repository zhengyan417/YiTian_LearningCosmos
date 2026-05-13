"""This file contains the prompts for the agent."""

import os
from datetime import datetime
from typing import Optional

from app.core.config import settings

_PROMPTS_DIR = os.path.dirname(__file__)


def _read(name: str) -> str:
    with open(os.path.join(_PROMPTS_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


# Read templates once at module load — no file I/O per request
_SYSTEM_PROMPT_TEMPLATE = _read("system.md")
SESSION_TITLE_PROMPT = _read("session_title.md")
_RESEARCH_PLANNER_TEMPLATE = _read("research_planner.md")
_RESEARCH_SUBAGENT_TEMPLATE = _read("research_subagent.md")
_RESEARCH_SYNTHESIS_TEMPLATE = _read("research_synthesis.md")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_system_prompt(username: Optional[str] = None, **kwargs):
    """Load the system prompt from the cached template."""
    user_context = f"# User\nYou are talking to {username}.\n" if username else ""
    return _SYSTEM_PROMPT_TEMPLATE.format(
        agent_name=settings.PROJECT_NAME + " Agent",
        current_date_and_time=_now(),
        user_context=user_context,
        **kwargs,
    )


def load_research_planner_prompt() -> str:
    """Load the research planner orchestrator prompt."""
    return _RESEARCH_PLANNER_TEMPLATE.format(
        current_date_and_time=_now(),
        max_subtasks=settings.RESEARCH_MAX_SUBTASKS,
    )


def load_research_subagent_prompt() -> str:
    """Load the research sub-agent prompt."""
    return _RESEARCH_SUBAGENT_TEMPLATE.format(
        current_date_and_time=_now(),
        max_searches=settings.RESEARCH_MAX_SEARCHES_PER_SUBAGENT,
    )


def load_research_synthesis_prompt(research_request: str, findings: str) -> str:
    """Load the research synthesis prompt with the original request and findings inlined."""
    return _RESEARCH_SYNTHESIS_TEMPLATE.format(
        current_date_and_time=_now(),
        research_request=research_request,
        findings=findings,
    )
