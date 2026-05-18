"""Langfuse trace post-hoc evaluator (offline, judge-based).

Pulls unscored traces from Langfuse over a lookback window, runs every
registered judge metric on each, and:

- pushes a numeric score per (trace, metric) back to Langfuse so dashboards
  light up;
- aggregates every case into an ``EvalReport`` persisted under
  ``evals/reports/trace_<timestamp>.json``.

This replaces the legacy ``evals/evaluator.py`` so it can speak to
``MultiAgentResponse``-shaped traces and share the LLM-judge primitive with
the routing / agent_quality runners.
"""

import asyncio
import time
from datetime import (
    datetime,
    timedelta,
)
from typing import Any

from colorama import (
    Style,
)
from langfuse import Langfuse
from langfuse.api.resources.commons.types.trace_with_details import TraceWithDetails
from tqdm import tqdm

from app.core.config import settings
from app.core.logging import logger
from evals.config import TRACE_EVAL_PASS_THRESHOLD
from evals.metrics import load_all_metrics
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
from evals.trace_eval.extractor import extract_io


class TraceEvaluator:
    """Score Langfuse traces against the metric library and persist results."""

    def __init__(self, lookback_hours: int = 24, limit: int = 100) -> None:
        """Initialize with a Langfuse client and a snapshot of the metric library.

        Args:
            lookback_hours: How far back (in hours) to pull traces from Langfuse.
            limit: Maximum traces to evaluate in one run.
        """
        self._langfuse = Langfuse(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            timeout=60,
        )
        self._lookback_hours = lookback_hours
        self._limit = limit
        self._metrics: dict[str, str] = load_all_metrics()  # name -> prompt
        if not self._metrics:
            logger.error("trace_eval_no_metrics_registered")

    async def run(self, write_report_file: bool = True) -> EvalReport:
        """Fetch + score traces and produce a final report."""
        start = time.time()
        report = new_report(eval_name="trace", model=settings.EVALUATION_LLM)

        if not self._metrics:
            report.duration_seconds = round(time.time() - start, 2)
            report.summary = {"error": "no metrics registered"}
            return report

        traces = self._fetch_traces()
        report.total = len(traces)

        for trace in tqdm(traces, desc="evaluating traces"):
            case = await self._score_trace(trace)
            report.cases.append(case)
            _bump_status(report, case.status)

            if settings.EVALUATION_SLEEP_TIME > 0:
                await asyncio.sleep(settings.EVALUATION_SLEEP_TIME)

        report.duration_seconds = round(time.time() - start, 2)
        report.summary = self._summarize(report)

        if write_report_file:
            write_report(report)
        logger.info(
            "trace_eval_completed",
            total=report.total,
            hits=report.hits,
            misses=report.misses,
            skipped=report.skipped,
            errors=report.errors,
            duration_seconds=report.duration_seconds,
        )
        return report

    async def _score_trace(self, trace: TraceWithDetails) -> CaseResult:
        """Run every metric on one trace and return the aggregated case result."""
        input_text, output_text = extract_io(trace)
        if input_text is None or output_text is None:
            return CaseResult(
                query=f"<trace {trace.id}>",
                status="skipped",
                note="could not extract input/output from trace",
            )

        preview = input_text if len(input_text) <= 300 else f"{input_text[:300]}..."
        case = CaseResult(query=preview)
        scored: dict[str, ScoreSchema] = {}

        try:
            for metric_name, metric_prompt in self._metrics.items():
                score = await call_judge(metric_prompt, input_text, output_text)
                if score is None:
                    continue
                scored[metric_name] = score
                self._push_score(trace, metric_name, score)
                case.metrics[metric_name] = round(score.score, 3)
        except Exception as e:
            logger.exception("trace_scoring_failed", trace_id=trace.id, error=str(e))
            case.status = "error"
            case.note = str(e)
            return case

        all_scored = len(scored) == len(self._metrics)
        if all_scored:
            case.status = "hit"
        else:
            case.status = "miss"
            missing = sorted(set(self._metrics) - set(scored))
            case.note = f"failed to score: {', '.join(missing)}"
        return case

    def _push_score(self, trace: TraceWithDetails, metric_name: str, score: ScoreSchema) -> None:
        """Write one numeric score back to Langfuse for dashboard pickup."""
        self._langfuse.create_score(
            trace_id=trace.id,
            name=metric_name,
            data_type="NUMERIC",
            value=score.score,
            comment=score.reasoning,
        )

    def _fetch_traces(self) -> list[TraceWithDetails]:
        """Return unscored traces from the configured lookback window."""
        cutoff = datetime.now() - timedelta(hours=self._lookback_hours)
        logger.info(
            "trace_eval_fetching_traces",
            from_timestamp=str(cutoff),
            limit=self._limit,
        )
        try:
            traces = self._langfuse.api.trace.list(
                from_timestamp=cutoff,
                order_by="timestamp.asc",
                limit=self._limit,
            ).data
            return [t for t in traces if not t.scores]
        except Exception as e:
            logger.error("trace_eval_fetch_failed", error=str(e))
            return []

    def _summarize(self, report: EvalReport) -> dict[str, Any]:
        """Build the per-metric averages + overall pass/fail flag for ``report.summary``."""
        per_metric: dict[str, dict[str, Any]] = {}
        for name in self._metrics:
            scores = [c.metrics[name] for c in report.cases if name in c.metrics]
            per_metric[name] = {
                "count": len(scores),
                "avg_score": round(sum(scores) / len(scores), 3) if scores else 0.0,
            }
        return {
            "accuracy": round(report.accuracy, 3),
            "pass_threshold": TRACE_EVAL_PASS_THRESHOLD,
            "passing": report.accuracy >= TRACE_EVAL_PASS_THRESHOLD,
            "per_metric": per_metric,
        }


def _bump_status(report: EvalReport, status: str) -> None:
    """Increment the matching counter on ``report`` for a case's outcome."""
    if status == "hit":
        report.hits += 1
    elif status == "miss":
        report.misses += 1
    elif status == "skipped":
        report.skipped += 1
    else:
        report.errors += 1


def print_summary(report: EvalReport) -> None:
    """Print a colored summary of one trace-eval run."""
    console.print_title("Trace Evaluation Summary")
    print(f"Model:    {report.model}")
    print(f"Duration: {report.duration_seconds}s")
    print(
        f"Total:    {report.total} "
        f"({report.hits} hits, {report.misses} misses, "
        f"{report.skipped} skipped, {report.errors} errors)"
    )
    acc = report.accuracy
    color = console.color_by_score(acc, warn=TRACE_EVAL_PASS_THRESHOLD)
    print(f"\nAccuracy: {color}{acc * 100:.1f}%{Style.RESET_ALL}")

    per_metric = report.summary.get("per_metric", {})
    if per_metric:
        print("\nPer-metric average score:")
        for name in sorted(per_metric):
            data = per_metric[name]
            score_color = console.color_by_score(data["avg_score"])
            print(f"  {name:24s} {score_color}{data['avg_score']:.2f}{Style.RESET_ALL}  (n={data['count']})")


async def run_default() -> EvalReport:
    """Convenience entry used by ``evals.main`` for the ``trace`` subcommand."""
    evaluator = TraceEvaluator()
    return await evaluator.run()
