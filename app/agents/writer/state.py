"""State schema for the writer agent's LangGraph workflow."""

from pydantic import (
    BaseModel,
    Field,
)


class WriterState(BaseModel):
    """State for the writer agent.

    Attributes:
        task: The user-provided writing task (instructions and/or source text).
        output: The drafted result text produced by the LLM node.
    """

    task: str = Field(default="", description="The writing task")
    output: str = Field(default="", description="The drafted output text")
