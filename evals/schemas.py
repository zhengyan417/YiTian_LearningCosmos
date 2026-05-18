"""Schemas shared by all eval runners.

- ``ScoreSchema``: one LLM-judge output (kept for backwards compatibility with
  the existing metric prompts in ``evals/metrics/prompts/``).
- ``CaseResult``: outcome of one offline eval case (routing / agent_quality).
- ``EvalReport``: top-level container persisted to ``evals/reports/`` by
  ``evals.shared.report.write_report``.
"""

from typing import (
    Any,
    Optional,
)

from pydantic import (
    BaseModel,
    Field,
)


class ScoreSchema(BaseModel):
    """One LLM-judge metric output."""

    score: float = Field(description="provide a score between 0 and 1")
    reasoning: str = Field(description="provide a one sentence reasoning")


class CaseResult(BaseModel):
    """Outcome of one offline eval case.

    ``expected`` and ``actual`` are typed ``Any`` so the same shape can carry
    routing eval data (list of agent names) and agent_quality eval data
    (free-form output text + scored metrics).
    """

    query: str = Field(description="the case input")
    expected: Any = Field(default=None, description="the expected value (shape depends on runner)")
    actual: Any = Field(default=None, description="the value the system actually produced")
    status: str = Field(default="", description='one of "hit" | "miss" | "skipped" | "error"')
    note: str = Field(default="", description="human-readable note (skip reason / error message)")
    metrics: dict[str, float] = Field(
        default_factory=dict,
        description="per-metric judge scores (used by agent_quality eval)",
    )


class EvalReport(BaseModel):
    """Top-level eval report produced by one runner invocation."""

    eval_name: str = Field(description="identifier for the eval (routing / trace / agent_<name>)")
    timestamp: str = Field(description="ISO-8601 start timestamp")
    model: Optional[str] = Field(default=None, description="judge / production model under test")
    duration_seconds: float = Field(default=0.0, description="wall-clock runtime in seconds")
    total: int = Field(default=0, description="total cases attempted")
    hits: int = Field(default=0, description="cases where actual matched expected")
    misses: int = Field(default=0, description="cases where actual did not match expected")
    skipped: int = Field(default=0, description="cases skipped (e.g. dependency missing)")
    errors: int = Field(default=0, description="cases that raised before producing a verdict")
    cases: list[CaseResult] = Field(default_factory=list, description="per-case results")
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="runner-specific aggregates (e.g. per-agent breakdown)",
    )

    @property
    def accuracy(self) -> float:
        """Hit rate over evaluated (non-skipped, non-errored) cases."""
        evaluated = self.hits + self.misses
        return (self.hits / evaluated) if evaluated else 0.0
