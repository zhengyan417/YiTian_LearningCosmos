"""Skill routing eval — measures how often the LLM picks the expected skill.

This is an offline integration check. It does NOT require Postgres or Langfuse —
it bypasses the LangGraph compilation path and calls ``llm_service`` directly with
all currently-registered skill tools bound. For each ``(query, expected_skill)``
pair in ``golden.jsonl`` we:

  1. Ask the production LLM (with skill tools bound) to respond once.
  2. Inspect the resulting ``tool_calls`` — the first one's tool name maps back
     to a skill via ``SkillRegistry``.
  3. Compare against ``expected_skill`` (use the literal ``"direct_answer"`` for
     "no tool call expected").
  4. Print a per-skill accuracy breakdown plus a list of mismatches for triage.

Cases whose ``expected_skill`` is not currently registered (e.g. ``code_ops``
without ``CODE_OPS_ALLOWED_ROOTS``) are SKIPPED with a clear notice — they don't
count against the accuracy score, so the eval stays meaningful in any
configuration.
"""

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import (
    dataclass,
    field,
)
from typing import (
    List,
    Optional,
)

import colorama
from colorama import (
    Fore,
    Style,
)
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
)

# Make the ``app`` package importable when this file is invoked as a script.
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.langgraph.skills import SkillRegistry  # noqa: E402
from app.core.prompts import load_system_prompt  # noqa: E402
from app.services.llm import llm_service  # noqa: E402

DIRECT_ANSWER = "direct_answer"
GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden.jsonl")
PASS_THRESHOLD = 0.7  # exit code 1 below this overall accuracy


@dataclass
class CaseResult:
    """One case outcome — what was asked, what we expected, what the LLM did."""

    query: str
    expected_skill: str
    actual_skill: Optional[str]
    tool_calls: List[str] = field(default_factory=list)
    status: str = ""  # "hit" | "miss" | "skipped" | "error"
    note: str = ""


def _load_golden() -> List[dict]:
    """Read non-empty / non-comment JSONL lines from ``golden.jsonl``."""
    cases: List[dict] = []
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                cases.append(json.loads(stripped))
            except json.JSONDecodeError as e:
                raise ValueError(f"golden.jsonl line {i} is not valid JSON: {e}") from e
    return cases


async def _run_one(case: dict, skill_by_tool: dict, registered_skills: set) -> CaseResult:
    """Execute one routing check; never raise — encode failures in the result."""
    query = case["query"]
    expected = case["expected_skill"]

    # If the expected skill isn't even registered, this case is not testable
    # in the current configuration. Skip rather than miscount it as a miss.
    if expected != DIRECT_ANSWER and expected not in registered_skills:
        return CaseResult(
            query=query,
            expected_skill=expected,
            actual_skill=None,
            status="skipped",
            note=f"skill '{expected}' is not registered in this configuration",
        )

    messages = [
        SystemMessage(
            content=load_system_prompt(
                long_term_memory="No relevant memory.",
                tool_usage_guide=SkillRegistry.render_usage_guide(),
            )
        ),
        HumanMessage(content=query),
    ]

    try:
        response = await llm_service.call(messages)
    except Exception as e:
        return CaseResult(
            query=query,
            expected_skill=expected,
            actual_skill=None,
            status="error",
            note=str(e),
        )

    tool_calls: List[str] = []
    if isinstance(response, AIMessage) and response.tool_calls:
        tool_calls = [tc["name"] for tc in response.tool_calls]
        actual_skill = skill_by_tool.get(tool_calls[0], "unknown")
    else:
        actual_skill = DIRECT_ANSWER

    return CaseResult(
        query=query,
        expected_skill=expected,
        actual_skill=actual_skill,
        tool_calls=tool_calls,
        status="hit" if actual_skill == expected else "miss",
    )


def _print_report(results: List[CaseResult]) -> int:
    """Print a markdown-ish stdout report. Return exit code based on accuracy."""
    by_status: dict = defaultdict(int)
    by_expected: dict = defaultdict(lambda: {"hit": 0, "miss": 0})
    misses: List[CaseResult] = []
    skipped: List[CaseResult] = []
    errors: List[CaseResult] = []

    for result in results:
        by_status[result.status] += 1
        if result.status in {"hit", "miss"}:
            by_expected[result.expected_skill][result.status] += 1
        if result.status == "miss":
            misses.append(result)
        elif result.status == "skipped":
            skipped.append(result)
        elif result.status == "error":
            errors.append(result)

    total_evaluated = by_status["hit"] + by_status["miss"]
    accuracy = (by_status["hit"] / total_evaluated) if total_evaluated else 0.0

    print()
    print(f"{Fore.CYAN}{Style.BRIGHT}Skill routing eval results{Style.RESET_ALL}")
    print("=" * 60)
    color = Fore.GREEN if accuracy >= 0.8 else Fore.YELLOW if accuracy >= PASS_THRESHOLD else Fore.RED
    print(
        f"Overall accuracy: {color}{accuracy * 100:5.1f}%{Style.RESET_ALL} "
        f"({by_status['hit']}/{total_evaluated} evaluated, "
        f"{len(skipped)} skipped, {len(errors)} errors)"
    )
    print()

    if by_expected:
        print("Per-skill accuracy:")
        for skill_name in sorted(by_expected):
            counts = by_expected[skill_name]
            total = counts["hit"] + counts["miss"]
            pct = counts["hit"] / total if total else 0
            color = Fore.GREEN if pct >= 0.8 else Fore.YELLOW if pct >= PASS_THRESHOLD else Fore.RED
            print(f"  {skill_name:24s} {color}{pct * 100:5.1f}%{Style.RESET_ALL} ({counts['hit']}/{total})")
        print()

    if misses:
        print(f"{Fore.RED}Mismatches ({len(misses)}):{Style.RESET_ALL}")
        for result in misses:
            print(f"  - query: {result.query!r}")
            print(
                f"    expected={result.expected_skill}, actual={result.actual_skill}, tool_calls={result.tool_calls}"
            )
        print()

    if skipped:
        print(f"{Fore.YELLOW}Skipped ({len(skipped)}):{Style.RESET_ALL}")
        for result in skipped:
            print(f"  - {result.expected_skill}: {result.query[:60]} — {result.note}")
        print()

    if errors:
        print(f"{Fore.RED}Errors ({len(errors)}):{Style.RESET_ALL}")
        for result in errors:
            print(f"  - {result.query[:60]} — {result.note}")
        print()

    return 0 if accuracy >= PASS_THRESHOLD else 1


async def main() -> int:
    """Eval entrypoint — returns the exit code for the calling script."""
    parser = argparse.ArgumentParser(description="Offline skill routing eval")
    parser.add_argument("--limit", type=int, default=None, help="cap how many cases to run")
    parser.add_argument("--concurrency", type=int, default=3, help="parallel LLM calls (default 3)")
    args = parser.parse_args()

    colorama.init()
    SkillRegistry.discover()
    skills = SkillRegistry.all()
    registered_skills = {s.name for s in skills}
    skill_by_tool = {tool.name: skill.name for skill in skills for tool in skill.tools}

    if not registered_skills:
        print(f"{Fore.RED}No skills registered — nothing to eval.{Style.RESET_ALL}")
        return 1

    print(f"{Fore.CYAN}Registered skills:{Style.RESET_ALL} {sorted(registered_skills)}")
    print(f"{Fore.CYAN}Bound tools:{Style.RESET_ALL} {sorted(skill_by_tool)}")

    # Bind skill tools onto the production LLM service for this run.
    llm_service.bind_tools([tool for skill in skills for tool in skill.tools])

    cases = _load_golden()
    if args.limit:
        cases = cases[: args.limit]
    print(f"Running {len(cases)} cases (concurrency={args.concurrency})…")

    semaphore = asyncio.Semaphore(args.concurrency)

    async def _bounded(case: dict) -> CaseResult:
        async with semaphore:
            return await _run_one(case, skill_by_tool, registered_skills)

    results = await asyncio.gather(*[_bounded(case) for case in cases])
    return _print_report(results)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
