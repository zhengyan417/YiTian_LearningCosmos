"""Path sandbox for the code_ops skill.

Every code_ops tool routes user/LLM-supplied paths through ``resolve_inside_root``
before touching the filesystem. The function fully resolves symlinks and
verifies the result is contained in one of ``settings.CODE_OPS_ALLOWED_ROOTS``,
so neither a leading ``..`` nor a malicious symlink can escape the sandbox.
"""

from pathlib import Path
from typing import (
    List,
    Optional,
)

from app.core.config import settings

# Directories that are pointless (or risky) for an LLM to inspect; the grep /
# list_dir tools skip them silently to avoid wasting tokens on vendored noise.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".idea",
        ".vscode",
    }
)

# Heuristic: a file is treated as binary if its first chunk contains a NUL byte.
# Cheap, defeats accidental reads of executables/images without pulling libmagic.
_BINARY_PROBE_BYTES = 8192


def get_allowed_roots() -> List[Path]:
    """Return resolved absolute Paths for every configured allowed root.

    Roots that don't exist on disk are dropped (they can't sandbox anything).
    """
    roots: List[Path] = []
    for raw in settings.CODE_OPS_ALLOWED_ROOTS:
        try:
            candidate = Path(raw).expanduser().resolve(strict=False)
        except OSError:
            continue
        if candidate.exists():
            roots.append(candidate)
    return roots


def resolve_inside_root(user_path: str) -> Optional[Path]:
    """Resolve ``user_path`` and confirm it stays inside an allowed root.

    Args:
        user_path: A path supplied by the LLM. May be absolute or relative; if
            relative it is resolved against the first allowed root.

    Returns:
        The fully resolved absolute Path when it is contained in some allowed
        root, or ``None`` if the path escapes every root (or no roots are
        configured at all).
    """
    roots = get_allowed_roots()
    if not roots:
        return None

    candidate = Path(user_path).expanduser()
    if not candidate.is_absolute():
        candidate = roots[0] / candidate

    try:
        resolved = candidate.resolve(strict=False)
    except OSError:
        return None

    for root in roots:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved
    return None


def is_binary(path: Path) -> bool:
    """Return True when the file looks binary (heuristic: contains a NUL byte)."""
    try:
        with path.open("rb") as f:
            chunk = f.read(_BINARY_PROBE_BYTES)
    except OSError:
        return True
    return b"\x00" in chunk
