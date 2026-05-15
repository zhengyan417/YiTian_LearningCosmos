"""Code ops skill — read-only filesystem inspection inside a configured sandbox."""

from app.core.langgraph.skills.base import Skill
from app.core.langgraph.skills.code_ops.tools import (
    code_detect_language,
    code_grep,
    code_list_dir,
    code_read_file,
)

code_ops_skill = Skill(
    name="code_ops",
    summary="Read, list, and grep files inside a configured code sandbox",
    when_to_use=(
        "The user has uploaded or pointed at a file/directory inside the sandbox "
        "and wants you to analyse, locate, or explain code. Start with code_list_dir "
        "or code_grep to discover, then code_read_file for full source."
    ),
    when_not_to_use=(
        "The user only wants new code written from scratch with no existing source to read. "
        "The path is outside the sandbox — instead, ask the user to place it under an "
        "allowed root rather than guessing. The question is about the public web (use "
        "web_research) or live data (use data_query when available)."
    ),
    examples=[
        "User: 'What does process_order do in the orders module?' → code_grep('def process_order', '<root>', '*.py') → code_read_file(hit_path)",
        "User: 'List the files under src/api' → code_list_dir('src/api')",
        "Before explaining a snippet → code_detect_language(path) to pick the right syntax conventions",
    ],
    tools=[code_read_file, code_list_dir, code_grep, code_detect_language],
)
