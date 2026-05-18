"""Adapt Langfuse traces of different shapes into ``(input_text, output_text)``.

The coordinator-based ``/chat`` endpoint produces traces whose ``output`` is a
``MultiAgentResponse`` (``answer`` + ``routing_reasoning`` + ``delegations``).
Pre-refactor chatbot traces exposed a ``messages`` list on ``trace.output``.

``extract_io`` tries the new shape first, falls back to the legacy shape, and
returns ``(None, None)`` when neither matches so the runner can mark the case
``skipped`` instead of erroring.
"""

from typing import (
    Optional,
    Tuple,
)

from langfuse.api.resources.commons.types.trace_with_details import TraceWithDetails


def _format_messages_legacy(messages: list[dict]) -> str:
    """Render the pre-refactor message list into plain text.

    Mirrors the old ``evals.helpers.format_messages`` semantics so traces from
    before the refactor still produce comparable input/output strings.
    """
    formatted: list[str] = []
    for idx, message in enumerate(messages):
        if message.get("type") == "tool":
            prev = messages[idx - 1] if idx > 0 else {}
            tool_calls = prev.get("additional_kwargs", {}).get("tool_calls") or prev.get("tool_calls") or []
            if tool_calls:
                args = tool_calls[0].get("function", {}).get("arguments") or tool_calls[0].get("args") or {}
            else:
                args = {}
            content = message.get("content") or ""
            tool_name = message.get("name") or "?"
            head = f"tool {tool_name} input: {args} "
            formatted.append(head + (f"{content[:100]}..." if len(content) > 100 else content))
        elif message.get("content"):
            formatted.append(f"{message.get('type')}: {message['content']}")
    return "\n".join(formatted)


def _from_multi_agent_response(trace: TraceWithDetails) -> Optional[Tuple[str, str]]:
    """Extract from a coordinator-produced trace.

    Trace shape:
        - ``trace.input``: ``{"query": "..."}`` or the raw query string.
        - ``trace.output``: ``{"answer": "...", ...}`` or the raw answer string.
    """
    input_text: Optional[str] = None
    if isinstance(trace.input, dict):
        query = trace.input.get("query")
        if isinstance(query, str) and query.strip():
            input_text = query
    elif isinstance(trace.input, str) and trace.input.strip():
        input_text = trace.input

    if input_text is None:
        return None

    output_text: Optional[str] = None
    if isinstance(trace.output, dict):
        answer = trace.output.get("answer")
        if isinstance(answer, str) and answer.strip():
            output_text = answer
    elif isinstance(trace.output, str) and trace.output.strip():
        output_text = trace.output

    if output_text is None:
        return None
    return input_text, output_text


def _from_legacy_messages(trace: TraceWithDetails) -> Optional[Tuple[str, str]]:
    """Extract from a pre-refactor trace where ``trace.output["messages"]`` carries the conversation."""
    if not isinstance(trace.output, dict):
        return None
    messages = trace.output.get("messages")
    if not isinstance(messages, list) or not messages:
        return None

    input_text = _format_messages_legacy(messages[:-1])
    output_text = _format_messages_legacy([messages[-1]])
    if not input_text or not output_text:
        return None
    return input_text, output_text


def extract_io(trace: TraceWithDetails) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(input, output)`` extracted from ``trace``, or ``(None, None)``.

    Tries the new MultiAgentResponse shape first, then the legacy messages
    shape. Returns ``(None, None)`` when neither matches so the caller can
    record the trace as ``skipped``.
    """
    for extractor in (_from_multi_agent_response, _from_legacy_messages):
        result = extractor(trace)
        if result is not None:
            return result
    return None, None
