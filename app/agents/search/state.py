"""State schema for the search agent's LangGraph workflow."""

from pydantic import (
    BaseModel,
    Field,
)


class SearchState(BaseModel):
    """State for the search agent.

    Attributes:
        task: The user's search query / narrow factual question.
        raw_results: Raw Tavily results (markdown). Populated by the search node.
        output: Final concise, cited answer. Populated by the summarize node.
    """

    task: str = Field(default="", description="The search query")
    raw_results: str = Field(default="", description="Raw Tavily search output")
    output: str = Field(default="", description="The final summarized answer")
