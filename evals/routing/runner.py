"""Coordinator routing accuracy eval — offline.

Replaces the legacy ``evals/skill_routing/`` runner. For each
``(query, expected_agents)`` pair in ``golden.jsonl`` we drive the coordinator's
``_route`` node directly (skipping dispatch + synthesize) and compare the
resulting delegation set against the expected one.

Match semantics: **multiset equality** of agent names. Order doesn't matter,
duplicates do. An empty ``expected_agents`` list means the coordinator should
answer directly (no specialist delegation).

The runner calls ``coordinator_agent._route`` directly so the eval tracks the
exact production routing path (including its fallback behavior on LLM failures).
"""

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import (
    Any,
    Optional,
)

from colorama import (
    Fore,
    Style,
)

from app.agents.coordinator.agent import coordinator_agent
from app.agents.coordinator.state import CoordinatorState
from app.core.logging import logger
from app.schemas.multi_agent import (
    Delegation,
    RoutingDecision,
)
from evals.config import (
    DIRECT_ANSWER,
    ROUTING_PASS_THRESHOLD,
)
from evals.schemas import (
    CaseResult,
    EvalReport,
)
from evals.shared import console
from evals.shared.report import (
    new_report,
    write_report,
)

GOLDEN_PATH = Path(__file__).parent / "golden.jsonl"


def _load_golden() -> list[dict[str, Any]]:
    """Read the golden file, skipping blank lines and ``#`` comments."""
    cases: list[dict[str, Any]] = []
    with GOLDEN_PATH.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                cases.append(json.loads(stripped))
            except json.JSONDecodeError as e:
                raise ValueError(f"golden.jsonl line {i}: invalid JSON: {e}") from e
    return cases


async def _route_once(query: str) -> Optional[RoutingDecision]:
    """Drive ``coordinator._route`` once for one query.

    Returns the resulting ``RoutingDecision`` extracted from the Command, or
    ``None`` when the routing call raised (the coordinator's own fallback path
    swallows LLM errors, so this should be rare).
    """
    state = CoordinatorState(query=query, context_id="routing-eval")
    try:
        cmd = await coordinator_agent._route(state)
    except Exception as e:
        logger.exception("routing_eval_route_failed", query=query[:100], error=str(e))
        return None

    raw_update = cmd.update
    update: dict[str, Any] = raw_update if isinstance(raw_update, dict) else {}
    delegations_raw = update.get("delegations") or []
    # delegations are Pydantic ``Delegation`` models when set via Command.update
    delegations: list[Delegation] = list(delegations_raw)
    return RoutingDecision(
        reasoning=str(update.get("routing_reasoning", "")),
        direct_answer=update.get("direct_answer"),
        delegations=delegations,
    )


def _actual_agents(decision: RoutingDecision) -> list[str]:
    """Sorted list of agent names from the decision (empty list = direct answer)."""
    return sorted(d.agent for d in decision.delegations)


def _is_match(expected: list[str], decision: RoutingDecision) -> bool:
    """Multiset equality between expected and actual delegated agents."""
    return _actual_agents(decision) == sorted(expected)


def _expected_label(expected: list[str]) -> str:
    """Human-readable key for grouping per-expected-routing accuracy in the report."""
    return "+".join(expected) if expected else DIRECT_ANSWER


async def _run_case(case: dict[str, Any], semaphore: asyncio.Semaphore) -> CaseResult:
    """Score one golden case end-to-end."""
    query: str = case["query"]
    expected_raw = case.get("expected_agents", [])
    expected: list[str] = sorted(expected_raw) if isinstance(expected_raw, list) else []

    async with semaphore:
        decision = await _route_once(query)

    if decision is None:
        return CaseResult(
            query=query,
            expected=expected,
            status="error",
            note="coordinator._route raised an exception (see logs)",
        )

    actual = _actual_agents(decision)
    matched = actual == expected
    return CaseResult(
        query=query,
        expected=expected,
        actual=actual,
        status="hit" if matched else "miss",
        note=case.get("comment", ""),
    )


async def run(concurrency: int = 3, limit: Optional[int] = None) -> EvalReport:
    """Run the full routing eval and return the populated report."""
    start = time.time()
    cases = _load_golden()
    if limit:
        cases = cases[:limit]

    report = new_report(eval_name="routing")
    report.total = len(cases)
    semaphore = asyncio.Semaphore(concurrency)

    results = await asyncio.gather(*[_run_case(c, semaphore) for c in cases])
    for result in results:
        report.cases.append(result)
        _bump_status(report, result.status)

    report.duration_seconds = round(time.time() - start, 2)
    report.summary = _summarize(report)
    write_report(report)
    logger.info(
        "routing_eval_completed",
        total=report.total,
        hits=report.hits,
        misses=report.misses,
        errors=report.errors,
        accuracy=round(report.accuracy, 3),
        duration_seconds=report.duration_seconds,
    )
    return report


def _bump_status(report: EvalReport, status: str) -> None:
    """Increment the matching counter on ``report`` for a case outcome."""
    if status == "hit":
        report.hits += 1
    elif status == "miss":
        report.misses += 1
    elif status == "skipped":
        report.skipped += 1
    else:
        report.errors += 1


def _summarize(report: EvalReport) -> dict[str, Any]:
    """Build per-expected-routing accuracy + overall pass/fail flag."""
    by_expected: dict[str, dict[str, int]] = defaultdict(lambda: {"hit": 0, "miss": 0})
    for case in report.cases:
        if case.status not in {"hit", "miss"}:
            continue
        expected = case.expected if isinstance(case.expected, list) else []
        by_expected[_expected_label(expected)][case.status] += 1

    per_expected = {
        key: {
            "hits": counts["hit"],
            "misses": counts["miss"],
            "accuracy": round(counts["hit"] / max(counts["hit"] + counts["miss"], 1), 3),
        }
        for key, counts in by_expected.items()
    }
    return {
        "accuracy": round(report.accuracy, 3),
        "pass_threshold": ROUTING_PASS_THRESHOLD,
        "passing": report.accuracy >= ROUTING_PASS_THRESHOLD,
        "per_expected": per_expected,
    }


def print_summary(report: EvalReport) -> int:
    """Print a colored summary and return an exit code (0 if passing)."""
    console.print_title("Routing Evaluation Summary")
    acc = report.accuracy
    color = console.color_by_score(acc, warn=ROUTING_PASS_THRESHOLD)
    evaluated = report.hits + report.misses
    print(
        f"Overall accuracy: {color}{acc * 100:.1f}%{Style.RESET_ALL} "
        f"({report.hits}/{evaluated} evaluated, "
        f"{report.skipped} skipped, {report.errors} errors)"
    )
    print(f"Duration: {report.duration_seconds}s\n")

    per_expected = report.summary.get("per_expected", {})
    if per_expected:
        print("Per-expected-routing accuracy:")
        for key in sorted(per_expected):
            data = per_expected[key]
            score_color = console.color_by_score(data["accuracy"], warn=ROUTING_PASS_THRESHOLD)
            ev = data["hits"] + data["misses"]
            print(f"  {key:32s} {score_color}{data['accuracy'] * 100:5.1f}%{Style.RESET_ALL} ({data['hits']}/{ev})")
        print()

    misses = [c for c in report.cases if c.status == "miss"]
    if misses:
        print(f"{Fore.RED}Mismatches ({len(misses)}):{Style.RESET_ALL}")
        for case in misses:
            print(f"  - query: {case.query!r}")
            print(f"    expected={case.expected}, actual={case.actual}")
            if case.note:
                print(f"    note: {case.note}")
        print()

    errors = [c for c in report.cases if c.status == "error"]
    if errors:
        print(f"{Fore.RED}Errors ({len(errors)}):{Style.RESET_ALL}")
        for case in errors:
            print(f"  - {case.query[:60]} — {case.note}")
        print()

    return 0 if acc >= ROUTING_PASS_THRESHOLD else 1


async def run_default() -> EvalReport:
    """Convenience entry used by ``evals.main`` for the ``routing`` subcommand."""
    return await run()


def main() -> int:
    """Standalone entry: ``python -m evals.routing.runner``."""
    parser = argparse.ArgumentParser(description="Coordinator routing accuracy eval")
    parser.add_argument("--limit", type=int, default=None, help="cap how many cases to run")
    parser.add_argument("--concurrency", type=int, default=3, help="parallel routing calls (default 3)")
    args = parser.parse_args()

    console.init()
    report = asyncio.run(run(concurrency=args.concurrency, limit=args.limit))
    return print_summary(report)


if __name__ == "__main__":
    sys.exit(main())
