"""Reusable LLM-judge primitive.

Every offline eval (routing, agent_quality, trace_eval) calls ``call_judge``
to score one ``(input, output)`` pair against a metric prompt. The judge uses
the dedicated ``settings.EVALUATION_*`` endpoint so it stays decoupled from the
production LLM service: no shared rate limit, no circular fallback, no tool
bindings leaking in.

We use ``chat.completions.create`` with ``response_format={"type": "json_object"}``
and parse the result manually rather than the OpenAI SDK's ``.parse()`` sugar.
DeepSeek (the default evaluation provider) rejects the strict ``json_schema``
response format the SDK emits, so we mirror the production coordinator's
approach instead.
"""

import asyncio
import json
from typing import (
    Any,
    Optional,
)

import openai
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import logger
from app.utils import extract_json
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


_JUDGE_INSTRUCTION = (
    "Reply with ONLY a JSON object — no prose, no markdown — with this shape:\n"
    '{"score": <float between 0 and 1>, "reasoning": "<one sentence>"}'
)


def _parse_score(raw: str) -> Optional[ScoreSchema]:
    """Parse the judge LLM's reply into a ``ScoreSchema``, tolerating fenced code blocks."""
    if not raw or not raw.strip():
        logger.warning("judge_response_empty")
        return None
    text = extract_json(raw)
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("judge_response_json_parse_failed", raw=raw[:200])
        return None
    try:
        return ScoreSchema.model_validate(data)
    except ValidationError as e:
        logger.warning("judge_response_schema_invalid", error=str(e), raw=raw[:200])
        return None


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
    user_message = f"Input: {input_text}\nGeneration: {output_text}\n\n{_JUDGE_INSTRUCTION}"

    last_error: Optional[Exception] = None
    for attempt in range(1, JUDGE_MAX_RETRIES + 1):
        try:
            response = await client.chat.completions.create(
                model=settings.EVALUATION_LLM,
                messages=[
                    {"role": "system", "content": metric_prompt},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            parsed = _parse_score(raw)
            if parsed is not None:
                return parsed
            # Parser failed — treat as a soft error so we still retry once or twice.
            last_error = ValueError(f"judge response not parseable as ScoreSchema: {raw[:200]}")
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
