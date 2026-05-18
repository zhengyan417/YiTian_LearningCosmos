"""Eval CLI dispatcher.

Subcommands:
    routing        — coordinator routing accuracy (offline golden set)
    agent <name>   — per-specialist quality (research / search / writer / coder)
    trace          — Langfuse trace post-hoc evaluation (online traffic)
    all            — run every eval in sequence

Each subcommand:
1. ``console.init()`` to enable colored output.
2. Runs the corresponding async runner.
3. Calls the runner's ``print_summary`` for colored stdout output.
4. Returns the runner's exit code (0 if passing, non-zero on failure).
"""

import argparse
import asyncio
import sys

from evals.agent_quality.runner import (
    AGENT_METRICS,
    print_summary as print_agent_summary,
    run as run_agent,
)
from evals.routing.runner import (
    print_summary as print_routing_summary,
    run as run_routing,
)
from evals.shared import console
from evals.trace_eval.runner import (
    TraceEvaluator,
    print_summary as print_trace_summary,
)


async def _do_routing(limit: int | None = None, concurrency: int = 3) -> int:
    """Run the routing accuracy eval."""
    report = await run_routing(concurrency=concurrency, limit=limit)
    return print_routing_summary(report)


async def _do_agent(name: str, limit: int | None = None, concurrency: int = 2) -> int:
    """Run the per-specialist quality eval for one agent."""
    if name not in AGENT_METRICS:
        print(
            f"unknown agent: {name}. available: {sorted(AGENT_METRICS)}",
            file=sys.stderr,
        )
        return 2
    report = await run_agent(name, concurrency=concurrency, limit=limit)
    return print_agent_summary(report)


async def _do_trace(hours: int = 24, limit: int = 100, write_file: bool = True) -> int:
    """Run the Langfuse trace post-hoc eval."""
    evaluator = TraceEvaluator(lookback_hours=hours, limit=limit)
    report = await evaluator.run(write_report_file=write_file)
    print_trace_summary(report)
    return 0 if report.total > 0 else 1


async def _do_all() -> int:
    """Run every eval in sequence; return the worst exit code observed."""
    codes: list[int] = []

    console.print_title("ALL: Routing")
    codes.append(await _do_routing())

    for agent in sorted(AGENT_METRICS):
        console.print_title(f"ALL: Agent — {agent}")
        codes.append(await _do_agent(agent))

    console.print_title("ALL: Trace")
    codes.append(await _do_trace())

    return max(codes) if codes else 0


def _parse() -> argparse.Namespace:
    """Build the argparse tree for the dispatcher."""
    parser = argparse.ArgumentParser(
        prog="python -m evals.main",
        description="Multi-agent eval framework",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_routing = sub.add_parser("routing", help="coordinator routing accuracy")
    p_routing.add_argument("--limit", type=int, default=None, help="cap how many cases to run")
    p_routing.add_argument("--concurrency", type=int, default=3, help="parallel routing calls")

    p_agent = sub.add_parser("agent", help="per-specialist quality")
    p_agent.add_argument("name", choices=sorted(AGENT_METRICS), help="which specialist to test")
    p_agent.add_argument("--limit", type=int, default=None, help="cap how many cases to run")
    p_agent.add_argument("--concurrency", type=int, default=2, help="parallel agent runs")

    p_trace = sub.add_parser("trace", help="Langfuse trace post-hoc eval")
    p_trace.add_argument("--hours", type=int, default=24, help="lookback window in hours")
    p_trace.add_argument("--limit", type=int, default=100, help="max traces per run")
    p_trace.add_argument("--no-report", action="store_true", help="skip writing the JSON report file")

    sub.add_parser("all", help="run every eval in sequence")

    return parser.parse_args()


def main() -> int:
    """Dispatch to the right subcommand and return its exit code."""
    args = _parse()
    console.init()

    if args.cmd == "routing":
        return asyncio.run(_do_routing(limit=args.limit, concurrency=args.concurrency))
    if args.cmd == "agent":
        return asyncio.run(_do_agent(args.name, limit=args.limit, concurrency=args.concurrency))
    if args.cmd == "trace":
        return asyncio.run(_do_trace(hours=args.hours, limit=args.limit, write_file=not args.no_report))
    if args.cmd == "all":
        return asyncio.run(_do_all())

    # argparse(required=True) should make this unreachable, but be explicit.
    return 2


if __name__ == "__main__":
    sys.exit(main())
