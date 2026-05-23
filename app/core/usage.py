"""Token accounting — per-request usage accumulation and CNY cost computation.

Every LLM call in the system flows through ``LLMService.call``; that one
chokepoint feeds ``record_llm_usage`` here. Usage lands in a per-request
``UsageAccumulator`` stored in a ``ContextVar``:

- The coordinator sets one in ``run_full`` — it captures the coordinator's own
  route/reflect/synthesize calls.
- Each A2A specialist executor sets a fresh one — it captures that specialist's
  calls (including the deep-research sub-graph) and ships the snapshot back to
  the coordinator as A2A artifact metadata.

ContextVars are copied into every child task an ``asyncio`` request spawns, so
concurrent in-request work shares one accumulator; a separate A2A request runs
in its own context and never contaminates the caller's accumulator.
"""

import contextvars
from collections import defaultdict
from typing import (
    Any,
    Optional,
)

from app.core.logging import logger
from app.schemas.usage import (
    ModelUsage,
    TokenUsage,
)

# RMB per 1M tokens. Pro uses the 75%-off promotional rate — edit these
# numbers when DeepSeek pricing changes.
RMB_PRICING: dict[str, dict[str, float]] = {
    "deepseek-v4-flash": {
        "input_cache_hit": 0.02,
        "input_cache_miss": 1,
        "output": 2,
    },
    "deepseek-v4-pro": {
        "input_cache_hit": 0.025,
        "input_cache_miss": 3,
        "output": 6,
    },
}

# Pricing fallback for an unrecognised model — keeps cost non-zero and logs.
_FALLBACK_MODEL = "deepseek-v4-flash"


def _price(model: str) -> dict[str, float]:
    """Return the per-1M-token price table for a model, matched by name prefix.

    Args:
        model: The model name as reported by the provider.

    Returns:
        The price table for the model, or the fallback model's table when the
        model is not recognised.
    """
    key = model.lower()
    for name, prices in RMB_PRICING.items():
        if key.startswith(name):
            return prices
    logger.warning("token_pricing_model_not_found", model=model, fallback=_FALLBACK_MODEL)
    return RMB_PRICING[_FALLBACK_MODEL]


def compute_cost(model: str, cache_miss_input: int, cache_hit_input: int, output: int) -> float:
    """Compute the CNY cost of one model's token consumption.

    Args:
        model: The model name as reported by the provider.
        cache_miss_input: Prompt tokens that missed the prompt cache.
        cache_hit_input: Prompt tokens served from the prompt cache.
        output: Completion tokens.

    Returns:
        The CNY cost, rounded to 8 decimal places.
    """
    prices = _price(model)
    cost = (
        cache_miss_input * prices["input_cache_miss"]
        + cache_hit_input * prices["input_cache_hit"]
        + output * prices["output"]
    ) / 1_000_000
    return round(cost, 8)


class _ModelCounter:
    """Mutable per-model token tally used internally by ``UsageAccumulator``."""

    def __init__(self) -> None:
        """Initialize all token counters to zero."""
        self.input_tokens: int = 0
        self.cached_input_tokens: int = 0
        self.output_tokens: int = 0


class UsageAccumulator:
    """Mutable per-request token tally, keyed by model.

    ``record`` contains no ``await``, so concurrent coroutines within the same
    request (e.g. the deep-research sub-agents) can record into a shared
    instance without a lock — the event loop cannot interleave them mid-call.
    """

    def __init__(self) -> None:
        """Initialize an empty accumulator."""
        self._by_model: dict[str, _ModelCounter] = defaultdict(_ModelCounter)
        self._llm_calls: int = 0

    def record(self, model: str, input_tokens: int, cached_input_tokens: int, output_tokens: int) -> None:
        """Add one LLM call's token usage to the tally.

        Args:
            model: The model name as reported by the provider.
            input_tokens: Prompt tokens (cache hit + miss).
            cached_input_tokens: Subset of ``input_tokens`` served from cache.
            output_tokens: Completion tokens.
        """
        counter = self._by_model[model]
        counter.input_tokens += input_tokens
        counter.cached_input_tokens += cached_input_tokens
        counter.output_tokens += output_tokens
        self._llm_calls += 1

    def snapshot(self) -> TokenUsage:
        """Build an immutable ``TokenUsage`` with per-model costs computed.

        Returns:
            A ``TokenUsage`` summarising every model recorded so far.
        """
        by_model: list[ModelUsage] = []
        total_input = total_cached = total_output = 0
        total_cost = 0.0

        for model, counter in self._by_model.items():
            cache_miss = max(counter.input_tokens - counter.cached_input_tokens, 0)
            cost = compute_cost(model, cache_miss, counter.cached_input_tokens, counter.output_tokens)
            by_model.append(
                ModelUsage(
                    model=model,
                    input_tokens=counter.input_tokens,
                    cached_input_tokens=counter.cached_input_tokens,
                    output_tokens=counter.output_tokens,
                    cost_cny=cost,
                )
            )
            total_input += counter.input_tokens
            total_cached += counter.cached_input_tokens
            total_output += counter.output_tokens
            total_cost += cost

        return TokenUsage(
            input_tokens=total_input,
            cached_input_tokens=total_cached,
            output_tokens=total_output,
            total_tokens=total_input + total_output,
            llm_calls=self._llm_calls,
            cost_cny=round(total_cost, 8),
            by_model=by_model,
        )


# Per-request accumulator. Set at the coordinator entry (``run_full``) and at
# every A2A specialist entry (``SpecialistAgentExecutor.execute``); ``None``
# outside any tracked request, in which case ``record_llm_usage`` is a no-op.
token_usage_var: contextvars.ContextVar[Optional[UsageAccumulator]] = contextvars.ContextVar(
    "token_usage_var", default=None
)


def _extract_usage(response: Any) -> Optional[tuple[str, int, int, int]]:
    """Pull ``(model, input_tokens, cached_input_tokens, output_tokens)`` from a response.

    Prefers LangChain's normalised ``usage_metadata``; falls back to the raw
    provider ``token_usage`` block (which is where DeepSeek-specific cache
    fields surface). Returns ``None`` when no usage is present at all.

    Args:
        response: The object returned by an LLM runnable — normally a
            ``BaseMessage``.

    Returns:
        A 4-tuple of usage figures, or ``None`` when the response carries none.
    """
    meta = getattr(response, "response_metadata", {}) or {}
    model = meta.get("model_name") or meta.get("model") or _FALLBACK_MODEL

    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata:
        details = usage_metadata.get("input_token_details") or {}
        return (
            str(model),
            int(usage_metadata.get("input_tokens", 0)),
            int(details.get("cache_read", 0)),
            int(usage_metadata.get("output_tokens", 0)),
        )

    token_usage = meta.get("token_usage") or {}
    if token_usage:
        cached = token_usage.get("prompt_cache_hit_tokens")
        if cached is None:
            cached = (token_usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
        return (
            str(model),
            int(token_usage.get("prompt_tokens", 0)),
            int(cached or 0),
            int(token_usage.get("completion_tokens", 0)),
        )

    return None


def record_llm_usage(response: Any) -> None:
    """Record one LLM response into the current request's accumulator.

    Never raises — a token-accounting bug must not break an LLM call. When no
    accumulator is set (untracked call path) this is a silent no-op.

    Args:
        response: The object returned by an LLM runnable.
    """
    try:
        accumulator = token_usage_var.get()
        if accumulator is None:
            return
        extracted = _extract_usage(response)
        if extracted is None:
            logger.debug("token_usage_missing_on_response")
            return
        model, input_tokens, cached_input_tokens, output_tokens = extracted
        accumulator.record(model, input_tokens, cached_input_tokens, output_tokens)
        logger.debug(
            "token_usage_recorded",
            model=model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
        )
    except Exception as e:
        logger.warning("token_usage_record_failed", error=str(e))


def aggregate_usage(parts: list[TokenUsage]) -> TokenUsage:
    """Sum several ``TokenUsage`` snapshots into one.

    Used by the coordinator to combine its own usage with every specialist's.

    Args:
        parts: The per-source usage snapshots to combine.

    Returns:
        A single ``TokenUsage`` with token counts, call counts, costs and the
        per-model breakdown all summed.
    """
    merged: dict[str, ModelUsage] = {}
    total_input = total_cached = total_output = total_calls = 0
    total_cost = 0.0

    for part in parts:
        total_input += part.input_tokens
        total_cached += part.cached_input_tokens
        total_output += part.output_tokens
        total_calls += part.llm_calls
        total_cost += part.cost_cny
        for entry in part.by_model:
            if entry.model not in merged:
                merged[entry.model] = ModelUsage(model=entry.model)
            agg = merged[entry.model]
            agg.input_tokens += entry.input_tokens
            agg.cached_input_tokens += entry.cached_input_tokens
            agg.output_tokens += entry.output_tokens
            agg.cost_cny = round(agg.cost_cny + entry.cost_cny, 8)

    return TokenUsage(
        input_tokens=total_input,
        cached_input_tokens=total_cached,
        output_tokens=total_output,
        total_tokens=total_input + total_output,
        llm_calls=total_calls,
        cost_cny=round(total_cost, 8),
        by_model=list(merged.values()),
    )
