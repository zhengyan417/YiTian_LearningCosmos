"""Shared constants and paths for the eval framework.

Each eval runner imports the small handful of values it needs from here so the
pass thresholds, retry budget, and report destination stay consistent and
adjustable in one place.
"""

from pathlib import Path

# Base paths
EVALS_DIR: Path = Path(__file__).parent
REPORTS_DIR: Path = EVALS_DIR / "reports"

# Pass thresholds — runners return non-zero exit codes below these values.
ROUTING_PASS_THRESHOLD: float = 0.7
AGENT_QUALITY_PASS_THRESHOLD: float = 0.7
TRACE_EVAL_PASS_THRESHOLD: float = 0.7

# LLM judge retry budget (used by ``evals.shared.judge``).
JUDGE_MAX_RETRIES: int = 3
JUDGE_RETRY_SLEEP_SECONDS: int = 10

# Sentinel meaning "the coordinator should answer directly, no specialist delegation".
# Used by the routing eval to encode "no-tool-call expected" cases.
DIRECT_ANSWER: str = "direct_answer"
