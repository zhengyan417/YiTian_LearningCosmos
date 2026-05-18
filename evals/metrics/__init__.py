"""LLM-judge metric prompt library.

Each ``*.md`` file under ``prompts/`` is a complete judge system prompt. Use
``load_metric(name)`` to read one, or ``load_all_metrics()`` to map every
metric name to its prompt text.
"""

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def list_metrics() -> list[str]:
    """Return all available metric names (stem of each ``prompts/<name>.md``)."""
    return sorted(p.stem for p in _PROMPTS_DIR.glob("*.md"))


def load_metric(name: str) -> str:
    """Load one judge prompt by name (e.g. ``"helpfulness"``)."""
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"metric prompt not found: {name} (at {path})")
    return path.read_text(encoding="utf-8")


def load_all_metrics() -> dict[str, str]:
    """Return a name → prompt dict for every metric in the prompts dir."""
    return {name: load_metric(name) for name in list_metrics()}
