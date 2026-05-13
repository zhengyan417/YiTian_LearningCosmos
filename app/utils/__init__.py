"""This file contains the utilities for the application."""

from .graph import (
    dump_messages,
    extract_text_content,
    prepare_messages,
    process_llm_response,
)


def extract_json(text: str) -> str:
    """Extract a JSON substring from LLM text output.

    Handles markdown code fences (`` ```json ... ``` ``) and stray
    surrounding text by finding the outermost ``{`` … ``}`` pair.
    """
    text = text.strip()
    if "```" in text:
        start = text.find("```")
        start = text.find("\n", start) + 1
        end = text.find("```", start)
        if end != -1:
            text = text[start:end].strip()
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        text = text[brace_start : brace_end + 1]
    return text


__all__ = [
    "dump_messages",
    "extract_json",
    "extract_text_content",
    "prepare_messages",
    "process_llm_response",
]
