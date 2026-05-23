"""Token usage and computed CNY cost schemas, surfaced in chat responses."""

from pydantic import (
    BaseModel,
    Field,
)


class ModelUsage(BaseModel):
    """Token usage and computed CNY cost for a single model.

    One entry is produced per model that actually answered a request — the
    LLM service can fall back between models, so a single agent may show more
    than one entry.

    Attributes:
        model: The model name as reported by the provider.
        input_tokens: Prompt tokens, including both cache hits and misses.
        cached_input_tokens: Subset of ``input_tokens`` served from cache.
        output_tokens: Completion tokens.
        cost_cny: Computed CNY cost for this model's portion of the work.
    """

    model: str = Field(..., description="Model name as reported by the provider")
    input_tokens: int = Field(default=0, description="Prompt tokens (cache hit + miss)")
    cached_input_tokens: int = Field(default=0, description="Prompt tokens served from cache")
    output_tokens: int = Field(default=0, description="Completion tokens")
    cost_cny: float = Field(default=0.0, description="Computed CNY cost for this model")


class TokenUsage(BaseModel):
    """Aggregate token usage and cost for one agent or one full chat round.

    Attached per-specialist on ``AgentResult`` and twice on
    ``MultiAgentResponse`` (the coordinator's own usage and the grand total).

    Attributes:
        input_tokens: Total prompt tokens across every LLM call.
        cached_input_tokens: Subset of ``input_tokens`` served from cache.
        output_tokens: Total completion tokens across every LLM call.
        total_tokens: ``input_tokens + output_tokens``.
        llm_calls: Number of LLM round-trips that contributed to this usage.
        cost_cny: Total computed CNY cost.
        by_model: Per-model breakdown of the usage above.
    """

    input_tokens: int = Field(default=0, description="Total prompt tokens")
    cached_input_tokens: int = Field(default=0, description="Prompt tokens served from cache")
    output_tokens: int = Field(default=0, description="Total completion tokens")
    total_tokens: int = Field(default=0, description="input_tokens + output_tokens")
    llm_calls: int = Field(default=0, description="Number of LLM round-trips")
    cost_cny: float = Field(default=0.0, description="Total computed CNY cost")
    by_model: list[ModelUsage] = Field(default_factory=list, description="Per-model usage breakdown")
