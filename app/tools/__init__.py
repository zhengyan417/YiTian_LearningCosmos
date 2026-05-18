"""Shared LangGraph tools used by multiple agents.

Currently only ``tavily_search`` (used by the research and search agents).
Kept as a top-level package so any agent can ``from app.tools import ...``
without crossing into another agent's namespace.
"""

from app.tools.tavily_search import tavily_search

__all__ = ["tavily_search"]
