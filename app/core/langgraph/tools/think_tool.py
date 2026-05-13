"""Strategic reflection tool for the deep research workflow.

This tool deliberately produces no external side-effect — its purpose is to
force the LLM to pause and reason about progress between searches, which
empirically improves research quality.
"""

from langchain_core.tools import tool


@tool(parse_docstring=True)
def think_tool(reflection: str) -> str:
    """Record a strategic reflection on research progress.

    Use this AFTER each search to analyze results and plan next steps. This
    creates a deliberate pause for quality decision-making.

    Use this tool to address:
    - What key information did I just find?
    - What's still missing?
    - Do I have enough to answer the question now?
    - What should the next search focus on, if any?

    Args:
        reflection: Detailed reflection on findings, gaps, and next steps.

    Returns:
        Confirmation that the reflection was recorded.
    """
    return f"Reflection recorded: {reflection}"
