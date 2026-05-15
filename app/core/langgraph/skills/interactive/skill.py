"""Interactive skill: human-in-the-loop confirmation and clarification.

Wraps ``ask_human`` so the LLM has a single, well-described escape hatch when
it needs the user to clarify intent or approve an irreversible action. Lives
in its own skill rather than ``web_research`` because it is orthogonal to
search — every other skill may need to call back to the user.
"""

from app.core.langgraph.skills.base import Skill
from app.core.langgraph.tools.ask_human import ask_human

interactive_skill = Skill(
    name="interactive",
    summary="Pause and ask the human for clarification or confirmation",
    when_to_use=(
        "The user's intent is ambiguous and a wrong guess would waste a tool call. "
        "You are about to perform an irreversible or sensitive action (delete, send, purchase). "
        "A previous tool failed twice and you need the user to choose between fallback options."
    ),
    when_not_to_use=(
        "You can answer or act with reasonable confidence — do not stall on small details. "
        "The user has already supplied the missing piece earlier in the conversation."
    ),
    examples=[
        "Ambiguous query 'cancel the last one' → ask_human('Cancel the last order or the last message?')",
        "About to delete a record → ask_human('Confirm deleting record #42? This cannot be undone.')",
    ],
    tools=[ask_human],
)
