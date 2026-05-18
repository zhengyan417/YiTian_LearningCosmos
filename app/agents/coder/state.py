"""State schema for the coder agent's LangGraph workflow."""

from pydantic import (
    BaseModel,
    Field,
)


class CoderState(BaseModel):
    """State for the coder agent.

    Attributes:
        task: The user's programming question or coding request.
        output: The code + explanation produced by the LLM node.
    """

    task: str = Field(default="", description="The programming task")
    output: str = Field(default="", description="The code answer text")
