"""Deep research proxy skill — exposes DeepResearchAgent as a single LLM-callable tool."""

from app.core.langgraph.skills.base import (
    ADVANCED_TIER,
    Skill,
)
from app.core.langgraph.skills.deep_research_proxy.proxy_tool import deep_research

deep_research_proxy_skill = Skill(
    name="deep_research_proxy",
    summary="Multi-step research with parallel sub-agents (HEAVY)",
    tier=ADVANCED_TIER,
    when_to_use=(
        "The user explicitly asks for an in-depth report, comparison, or structured "
        "research output; the question requires synthesizing multiple sources and "
        "would not be answered well by 1-2 simple searches."
    ),
    when_not_to_use=(
        "A single tavily_search would answer the question — prefer the cheaper path. "
        "The user wants a quick answer or is making conversation. "
        "You have not yet attempted a simpler search."
    ),
    examples=[
        "User: 'Give me a thorough comparison of Postgres vs MySQL for OLAP workloads' → deep_research(query)",
        "User: 'Research the EU AI Act's impact on open-source models' → deep_research(query)",
    ],
    tools=[deep_research],
)
