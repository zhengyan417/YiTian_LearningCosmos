"""Reusable LLM-judge primitive.

Every offline eval (routing, agent_quality, trace_eval) calls ``call_judge``
to score one ``(input, output)`` pair against a metric prompt. The judge uses
the dedicated ``settings.EVALUATION_*`` endpoint so it stays decoupled from the
production LLM service: no shared rate limit, no circular fallback, no tool
bindings leaking in.
"""

import asyncio
from typing import Optional

import openai
from openai import AsyncOpenAI

from app.core.config import settings
from app.core.logging import logger
from evals.config import (
    JUDGE_MAX_RETRIES,
    JUDGE_RETRY_SLEEP_SECONDS,
)
from evals.schemas import ScoreSchema

_client: Optional[AsyncOpenAI] = None


def _client_singleton() -> AsyncOpenAI:
    """Return the lazily-constructed async OpenAI client for the judge endpoint."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.EVALUATION_API_KEY,
            base_url=settings.EVALUATION_BASE_URL,
        )
    return _client


async def call_judge(
    metric_prompt: str,
    input_text: str,
    output_text: str,
) -> Optional[ScoreSchema]:
    """Score one ``(input, output)`` pair against a metric prompt.

    Args:
        metric_prompt: System prompt of the metric (one of
            ``evals/metrics/prompts/*.md``).
        input_text: The input that was given to the production system.
        output_text: The output the production system produced.

    Returns:
        ``ScoreSchema`` on success; ``None`` after all retries fail or when any
        of the inputs is empty.
    """
    if not metric_prompt or not input_text or not output_text:
        logger.warning(
            "judge_call_skipped_empty_field",
            has_prompt=bool(metric_prompt),
            has_input=bool(input_text),
            has_output=bool(output_text),
        )
        return None

    client = _client_singleton()
    last_error: Optional[Exception] = None
    for attempt in range(1, JUDGE_MAX_RETRIES + 1):
        try:
            response = await client.beta.chat.completions.parse(
                model=settings.EVALUATION_LLM,
                messages=[
                    {"role": "system", "content": metric_prompt},
                    {"role": "user", "content": f"Input: {input_text}\nGeneration: {output_text}"},
                ],
                response_format=ScoreSchema,
            )
            return response.choices[0].message.parsed
        except (openai.APIError, openai.OpenAIError) as e:
            last_error = e
            logger.warning(
                "judge_call_failed_retrying",
                attempt=attempt,
                max_attempts=JUDGE_MAX_RETRIES,
                error=str(e),
            )
            if attempt < JUDGE_MAX_RETRIES:
                await asyncio.sleep(JUDGE_RETRY_SLEEP_SECONDS)

    logger.error("judge_call_exhausted_retries", error=str(last_error) if last_error else "unknown")
    return None
