"""Multi-agent proxy skill — exposes the A2A coordinator as a single LLM-callable tool."""

from app.core.langgraph.skills.base import (
    ADVANCED_TIER,
    Skill,
)
from app.core.langgraph.skills.multi_agent_proxy.proxy_tool import multi_agent_delegate

multi_agent_proxy_skill = Skill(
    name="multi_agent_proxy",
    summary="Coordinate multiple A2A specialists for cross-domain tasks (HEAVY)",
    tier=ADVANCED_TIER,
    when_to_use=(
        "The user's task spans 2+ specialist domains (research + writing + code, etc.) "
        "and would benefit from specialist collaboration; you've judged that no single "
        "skill is sufficient on its own."
    ),
    when_not_to_use=(
        "A single skill (web_research, deep_research_proxy, …) would do — avoid the "
        "double LLM-routing overhead. You have not yet tried the simpler path. "
        "The task is conversational or trivially answerable."
    ),
    examples=[
        "User: 'Research Python 3.13 changes, then write a migration guide with code examples' → multi_agent_delegate(task)",
        "User: 'Pull the latest LLM benchmark results and summarize them in a weekly newsletter format' → multi_agent_delegate(task)",
    ],
    tools=[multi_agent_delegate],
)
