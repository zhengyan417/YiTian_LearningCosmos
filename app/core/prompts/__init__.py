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
_A2A_COORDINATOR_ROUTER_TEMPLATE = _read("a2a_coordinator_router.md")
_A2A_COORDINATOR_SYNTHESIS_TEMPLATE = _read("a2a_coordinator_synthesis.md")
_A2A_SEARCH_TEMPLATE = _read("a2a_search.md")
_A2A_WRITER_TEMPLATE = _read("a2a_writer.md")
_A2A_CODER_TEMPLATE = _read("a2a_coder.md")


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


def load_a2a_coordinator_router_prompt() -> str:
    """Load the A2A coordinator routing prompt."""
    return _A2A_COORDINATOR_ROUTER_TEMPLATE.format(current_date_and_time=_now())


def load_a2a_coordinator_synthesis_prompt(query: str, findings: str) -> str:
    """Load the A2A coordinator synthesis prompt with the user query and specialist findings inlined."""
    return _A2A_COORDINATOR_SYNTHESIS_TEMPLATE.format(
        current_date_and_time=_now(),
        query=query,
        findings=findings,
    )


def load_a2a_search_prompt() -> str:
    """Load the A2A search specialist system prompt."""
    return _A2A_SEARCH_TEMPLATE.format(current_date_and_time=_now())


def load_a2a_writer_prompt() -> str:
    """Load the A2A writer specialist system prompt."""
    return _A2A_WRITER_TEMPLATE.format(current_date_and_time=_now())


def load_a2a_coder_prompt() -> str:
    """Load the A2A coder specialist system prompt."""
    return _A2A_CODER_TEMPLATE.format(current_date_and_time=_now())
