"""Web research skill: search → fetch → reflect.

Bundles the ``tavily_search`` (discovery), ``fetch_url`` (full-page read), and
``think_tool`` (deliberate reflection) atomic tools into one skill the main
agent invokes for any external/realtime information need.
"""

from app.core.langgraph.skills.base import Skill
from app.core.langgraph.tools.fetch_url import fetch_url
from app.core.langgraph.tools.tavily_search import tavily_search
from app.core.langgraph.tools.think_tool import think_tool

web_research_skill = Skill(
    name="web_research",
    summary="Search the public web and read source pages",
    when_to_use=(
        "The user asks about realtime / external / breaking information; "
        "you need to verify a claim against primary sources; "
        "you need a search → reflect → re-search loop to refine an answer."
    ),
    when_not_to_use=(
        "The answer is already in the conversation, system prompt, or long-term memory. "
        "The user is asking about internal project state. "
        "A single direct answer is obviously sufficient."
    ),
    examples=[
        "User: What did the Fed announce today? → tavily_search('Federal Reserve announcement 2026-05-15')",
        "User: Open https://example.com/post and summarize it → fetch_url('https://example.com/post')",
        "After a weak first search → think_tool('first pass missed X, retry with Y') → tavily_search(Y)",
    ],
    tools=[tavily_search, fetch_url, think_tool],
)
