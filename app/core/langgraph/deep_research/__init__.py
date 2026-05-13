"""Deep Research multi-agent workflow.

Public surface:
    - DeepResearchAgent: orchestrator that plans, dispatches sub-agents in
      parallel, and synthesizes the final report.
"""

from app.core.langgraph.deep_research.graph import DeepResearchAgent

__all__ = ["DeepResearchAgent"]
