"""State schema for the coder agent's LangGraph workflow."""

from typing import Literal

from pydantic import (
    BaseModel,
    Field,
)


class CoderState(BaseModel):
    """State for the coder agent's ``code → review → END`` workflow.

    The graph runs in two phases. The ``code`` node fills ``draft``; the
    ``review`` node either keeps the draft (``verdict="accept"``) or replaces
    it with a revised version (``verdict="revise"``). ``output`` always holds
    the final answer returned to the caller, regardless of which branch ran.

    Attributes:
        task: The user's programming question or coding request.
        draft: The first-pass code answer produced by the ``code`` node.
        output: The final code answer returned to the caller. Equals ``draft``
            when the critic accepts, or the revised version when the critic
            requests changes.
        verdict: Whether the critic accepted the draft or revised it. ``""``
            when the review node has not run (reflection disabled or skipped).
        issues: The critic's notes on what was wrong with the draft. Empty
            string when the critic accepts or when reflection is disabled.
    """

    task: str = Field(default="", description="The programming task")
    draft: str = Field(default="", description="First-pass code answer before review")
    output: str = Field(default="", description="The final code answer text")
    verdict: Literal["", "accept", "revise"] = Field(
        default="",
        description="Critic verdict on the draft; empty when reflection is disabled or skipped",
    )
    issues: str = Field(default="", description="Critic-reported issues with the draft (empty if accepted)")
