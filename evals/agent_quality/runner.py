"""Per-specialist offline quality eval.

For each agent under test, the runner:

1. Loads a small golden set of representative tasks from
   ``evals/agent_quality/goldens/<agent>.jsonl``.
2. Runs ``agent.run(task, context_id)`` to get a real output.
3. Scores the output with a per-agent stack of LLM-judge metrics.
4. Marks the case ``hit`` when its mean adjusted score crosses
   ``AGENT_QUALITY_PASS_THRESHOLD``; ``miss`` otherwise.

"Adjusted" means scores for metrics where lower-is-better (hallucination,
toxicity) are inverted before averaging, so the mean is consistently
higher-is-better.

Each runner invocation tests exactly one agent so the budget can be controlled
— research in particular costs tens of seconds + Tavily quota per case.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import (
    Any,
    Optional,
)

from colorama import (
    Fore,
    Style,
)

from app.agents import AGENT_REGISTRY
from app.core.logging import logger
from evals.config import AGENT_QUALITY_PASS_THRESHOLD
from evals.metrics import load_metric
from evals.schemas import (
    CaseResult,
    EvalReport,
    ScoreSchema,
)
from evals.shared import console
from evals.shared.judge import call_judge
from evals.shared.report import (
    new_report,
    write_report,
)

GOLDENS_DIR = Path(__file__).parent / "goldens"

# Metrics where a *lower* judge score is better. Their scores get flipped
# (1 - x) before averaging so the mean is always higher-is-better.
INVERTED_METRICS: set[str] = {"hallucination", "toxicity"}

# Per-agent metric stack — name -> ordered judge metric names resolved against
# ``evals/metrics/prompts/*.md``. Keep stacks minimal — every extra metric
# multiplies the eval's LLM bill.
AGENT_METRICS: dict[str, list[str]] = {
    "research": ["helpfulness", "hallucination", "citation_coverage"],
    "search": ["helpfulness", "relevancy", "conciseness"],
    "writer": ["helpfulness", "conciseness"],
    "coder": ["helpfulness", "code_quality", "relevancy"],
}


def _adjusted(metric_name: str, raw_score: float) -> float:
    """Flip score for inverted metrics so larger is always better."""
    return 1.0 - raw_score if metric_name in INVERTED_METRICS else raw_score


def _load_golden(agent_name: str) -> list[dict[str, Any]]:
    """Read ``goldens/<agent>.jsonl`` (blank lines and ``#`` comments skipped)."""
    path = GOLDENS_DIR / f"{agent_name}.jsonl"
    cases: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                cases.append(json.loads(stripped))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path.name} line {i}: invalid JSON: {e}") from e
    return cases


def _load_agent_metrics(agent_name: str) -> dict[str, str]:
    """Load only the metric prompts this agent will be scored against."""
    return {name: load_metric(name) for name in AGENT_METRICS[agent_name]}


async def _prewarm_agent(agent: Any, agent_name: str) -> bool:
    """Force graph compilation (and connection pool init for research)."""
    try:
        maybe_coro = agent.create_graph()
        if hasattr(maybe_coro, "__await__"):
            await maybe_coro
        return True
    except Exception as e:
        logger.exception("agent_quality_prewarm_failed", agent=agent_name, error=str(e))
        return False


async def _run_case(
    agent_name: str,
    agent: Any,
    case: dict[str, Any],
    metric_prompts: dict[str, str],
    semaphore: asyncio.Semaphore,
) -> CaseResult:
    """Run one task through the agent and score the output with each metric."""
    query: str = case["query"]
    context_id = f"quality-{agent_name}-{uuid.uuid4().hex[:8]}"

    async with semaphore:
        try:
            output = await agent.run(query, context_id)
        except Exception as e:
            logger.exception(
                "agent_quality_run_failed",
                agent=agent_name,
                query=query[:100],
                error=str(e),
            )
            return CaseResult(
                query=query,
                status="error",
                note=f"agent.run raised: {e}",
            )

    if not output or not output.strip():
        return CaseResult(
            query=query,
            actual="<empty>",
            status="error",
            note="agent returned empty output",
        )

    preview = output[:500] + ("..." if len(output) > 500 else "")
    case_result = CaseResult(query=query, actual=preview)

    for metric_name, metric_prompt in metric_prompts.items():
        score: Optional[ScoreSchema] = await call_judge(metric_prompt, query, output)
        if score is None:
            logger.warning(
                "agent_quality_metric_failed",
                agent=agent_name,
                metric=metric_name,
                query=query[:100],
            )
            continue
        case_result.metrics[metric_name] = round(score.score, 3)

    if not case_result.metrics:
        case_result.status = "error"
        case_result.note = "no metric produced a score"
        return case_result

    adjusted_avg = sum(_adjusted(n, v) for n, v in case_result.metrics.items()) / len(case_result.metrics)
    case_result.status = "hit" if adjusted_avg >= AGENT_QUALITY_PASS_THRESHOLD else "miss"
    if case_result.status == "miss":
        case_result.note = f"adjusted mean {adjusted_avg:.2f} below threshold {AGENT_QUALITY_PASS_THRESHOLD}"
    return case_result


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


def _summarize(report: EvalReport, agent_name: str) -> dict[str, Any]:
    """Per-metric averages (raw + adjusted) plus overall pass/fail flag."""
    metric_names = AGENT_METRICS[agent_name]
    per_metric: dict[str, dict[str, Any]] = {}
    for name in metric_names:
        scores = [c.metrics[name] for c in report.cases if name in c.metrics]
        if not scores:
            per_metric[name] = {
                "count": 0,
                "raw_avg": 0.0,
                "adjusted_avg": 0.0,
                "inverted": name in INVERTED_METRICS,
            }
            continue
        raw_avg = sum(scores) / len(scores)
        adjusted_avg = sum(_adjusted(name, s) for s in scores) / len(scores)
        per_metric[name] = {
            "count": len(scores),
            "raw_avg": round(raw_avg, 3),
            "adjusted_avg": round(adjusted_avg, 3),
            "inverted": name in INVERTED_METRICS,
        }
    return {
        "agent": agent_name,
        "accuracy": round(report.accuracy, 3),
        "pass_threshold": AGENT_QUALITY_PASS_THRESHOLD,
        "passing": report.accuracy >= AGENT_QUALITY_PASS_THRESHOLD,
        "per_metric": per_metric,
    }


async def run(agent_name: str, concurrency: int = 2, limit: Optional[int] = None) -> EvalReport:
    """Run the quality eval for one specialist agent."""
    if agent_name not in AGENT_METRICS:
        raise ValueError(f"unknown agent: {agent_name}. available: {sorted(AGENT_METRICS)}")

    start = time.time()
    agents = AGENT_REGISTRY()
    if agent_name not in agents:
        raise ValueError(f"agent not in registry: {agent_name}. available: {sorted(agents)}")
    agent = agents[agent_name]

    cases = _load_golden(agent_name)
    if limit:
        cases = cases[:limit]

    metric_prompts = _load_agent_metrics(agent_name)
    report = new_report(eval_name=f"agent_{agent_name}")
    report.total = len(cases)
    semaphore = asyncio.Semaphore(concurrency)

    warmed = await _prewarm_agent(agent, agent_name)
    if not warmed:
        # Pool / graph init blew up — mark every case errored so the report
        # still reflects the eval attempt instead of silently passing zero cases.
        for case in cases:
            err = CaseResult(
                query=case["query"],
                status="error",
                note=f"agent {agent_name} could not be initialized (see logs)",
            )
            report.cases.append(err)
            _bump_status(report, err.status)
        report.duration_seconds = round(time.time() - start, 2)
        report.summary = _summarize(report, agent_name)
        write_report(report)
        return report

    results = await asyncio.gather(*[_run_case(agent_name, agent, c, metric_prompts, semaphore) for c in cases])
    for result in results:
        report.cases.append(result)
        _bump_status(report, result.status)

    report.duration_seconds = round(time.time() - start, 2)
    report.summary = _summarize(report, agent_name)
    write_report(report)
    logger.info(
        "agent_quality_completed",
        agent=agent_name,
        total=report.total,
        hits=report.hits,
        misses=report.misses,
        errors=report.errors,
        accuracy=round(report.accuracy, 3),
        duration_seconds=report.duration_seconds,
    )
    return report


def print_summary(report: EvalReport) -> int:
    """Print a colored summary and return an exit code (0 if passing)."""
    agent_name = report.summary.get("agent", "?")
    console.print_title(f"Agent Quality — {agent_name}")
    acc = report.accuracy
    color = console.color_by_score(acc, warn=AGENT_QUALITY_PASS_THRESHOLD)
    evaluated = report.hits + report.misses
    print(
        f"Pass rate: {color}{acc * 100:.1f}%{Style.RESET_ALL} "
        f"({report.hits}/{evaluated} evaluated, "
        f"{report.skipped} skipped, {report.errors} errors)"
    )
    print(f"Duration: {report.duration_seconds}s\n")

    per_metric = report.summary.get("per_metric", {})
    if per_metric:
        print("Per-metric average (adjusted: higher = better):")
        for name in sorted(per_metric):
            data = per_metric[name]
            score_color = console.color_by_score(data["adjusted_avg"])
            tag = " (inv)" if data.get("inverted") else ""
            print(
                f"  {name:24s} adj={score_color}{data['adjusted_avg']:.2f}{Style.RESET_ALL}  "
                f"raw={data['raw_avg']:.2f}{tag}  (n={data['count']})"
            )
        print()

    misses = [c for c in report.cases if c.status == "miss"]
    if misses:
        print(f"{Fore.YELLOW}Below-threshold ({len(misses)}):{Style.RESET_ALL}")
        for case in misses:
            print(f"  - query: {case.query[:80]}")
            print(f"    scores: {case.metrics}")
            if case.note:
                print(f"    note: {case.note}")
        print()

    errors = [c for c in report.cases if c.status == "error"]
    if errors:
        print(f"{Fore.RED}Errors ({len(errors)}):{Style.RESET_ALL}")
        for case in errors:
            print(f"  - {case.query[:60]} — {case.note}")
        print()

    return 0 if acc >= AGENT_QUALITY_PASS_THRESHOLD else 1


async def run_default(agent_name: str) -> EvalReport:
    """Convenience entry used by ``evals.main`` for the ``agent <name>`` subcommand."""
    return await run(agent_name)


def main() -> int:
    """Standalone entry: ``python -m evals.agent_quality.runner <agent>``."""
    parser = argparse.ArgumentParser(description="Per-specialist offline quality eval")
    parser.add_argument(
        "agent",
        choices=sorted(AGENT_METRICS),
        help="which specialist agent to test",
    )
    parser.add_argument("--limit", type=int, default=None, help="cap how many cases to run")
    parser.add_argument("--concurrency", type=int, default=2, help="parallel agent runs (default 2)")
    args = parser.parse_args()

    console.init()
    report = asyncio.run(run(args.agent, concurrency=args.concurrency, limit=args.limit))
    return print_summary(report)


if __name__ == "__main__":
    sys.exit(main())
