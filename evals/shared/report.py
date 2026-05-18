"""Eval report writer.

Every runner produces a single ``EvalReport`` (see ``evals.schemas``) and hands
it to ``write_report`` which persists it as pretty-printed JSON under
``evals/reports/<eval_name>_<timestamp>.json``.
"""

import json
from datetime import datetime
from pathlib import Path

from app.core.logging import logger
from evals.config import REPORTS_DIR
from evals.schemas import EvalReport


def new_report(eval_name: str, model: str | None = None) -> EvalReport:
    """Start a fresh report stamped with the current timestamp.

    Args:
        eval_name: Short identifier used in the output filename
            (e.g. ``"routing"``, ``"agent_research"``).
        model: Optional model name to record (judge or production model).
    """
    return EvalReport(
        eval_name=eval_name,
        timestamp=datetime.now().isoformat(),
        model=model,
    )


def write_report(report: EvalReport) -> Path:
    """Persist the report as pretty-printed JSON and return the path."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"{report.eval_name}_{stamp}.json"

    with path.open("w", encoding="utf-8") as f:
        json.dump(report.model_dump(), f, indent=2, ensure_ascii=False)

    logger.info("eval_report_written", eval_name=report.eval_name, path=str(path))
    return path
