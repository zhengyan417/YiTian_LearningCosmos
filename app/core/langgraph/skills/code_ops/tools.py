"""Read-only filesystem tools for the code_ops skill.

Every tool routes its path argument through ``resolve_inside_root`` before
touching disk. Heavy work (read, walk, grep) is dispatched to a thread via
``asyncio.to_thread`` so a slow filesystem can't stall the FastAPI event loop.
"""

import asyncio
import re
from pathlib import Path
from typing import (
    List,
    Tuple,
)

from langchain_core.tools import tool

from app.core.config import settings
from app.core.langgraph.skills.code_ops.safety import (
    SKIP_DIRS,
    is_binary,
    resolve_inside_root,
)
from app.core.logging import logger

_LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".rb": "ruby",
    ".php": "php",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "csharp",
    ".swift": "swift",
    ".m": "objective-c",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".ps1": "powershell",
    ".sql": "sql",
    ".md": "markdown",
    ".markdown": "markdown",
    ".rst": "restructuredtext",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".dockerfile": "dockerfile",
    ".tf": "terraform",
}


def _read_file_sync(path: Path, max_bytes: int) -> str:
    """Read the file (blocking) and format the result for the LLM."""
    if not path.exists():
        return f"Error: file not found at '{path}'."
    if not path.is_file():
        return f"Error: '{path}' is not a regular file."
    if is_binary(path):
        return f"Error: '{path}' looks binary; refusing to read. Use a text file."

    size = path.stat().st_size
    truncated = size > max_bytes
    with path.open("rb") as f:
        raw = f.read(max_bytes)

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")

    suffix = (
        f"\n\n[truncated: showed first {max_bytes} of {size} bytes; "
        "request a narrower range or grep for relevant lines instead]"
        if truncated
        else ""
    )
    return f"# {path}\n\n```\n{text}\n```{suffix}"


def _list_dir_sync(path: Path, max_items: int) -> str:
    """List the directory (blocking) and format as a markdown table."""
    if not path.exists():
        return f"Error: directory not found at '{path}'."
    if not path.is_dir():
        return f"Error: '{path}' is not a directory."

    entries: List[Tuple[str, str, int]] = []
    try:
        children = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        return f"Error listing '{path}': {e}"

    for child in children:
        if child.name in SKIP_DIRS:
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        kind = "dir" if child.is_dir() else "file"
        entries.append((child.name, kind, 0 if kind == "dir" else stat.st_size))

    truncated = len(entries) > max_items
    entries = entries[:max_items]
    if not entries:
        return f"`{path}` is empty (or every entry was filtered)."

    lines = [f"# {path}", "", "| name | kind | size_bytes |", "| --- | --- | --- |"]
    for name, kind, size in entries:
        size_cell = "—" if kind == "dir" else str(size)
        lines.append(f"| {name} | {kind} | {size_cell} |")
    if truncated:
        lines.append(f"\n_(truncated to {max_items} entries)_")
    return "\n".join(lines)


def _grep_sync(pattern: str, root: Path, glob: str, max_matches: int, max_files: int) -> str:
    """Recursively grep for ``pattern`` under ``root`` (blocking)."""
    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: invalid regex pattern: {e}"

    matches: List[str] = []
    files_scanned = 0

    for file_path in root.rglob(glob):
        if files_scanned >= max_files:
            matches.append(f"\n_(stopped after scanning {max_files} files; narrow your glob)_")
            break
        if any(part in SKIP_DIRS for part in file_path.parts):
            continue
        if not file_path.is_file():
            continue
        if is_binary(file_path):
            continue

        files_scanned += 1
        try:
            with file_path.open("r", encoding="utf-8", errors="replace") as f:
                for lineno, line in enumerate(f, start=1):
                    if regex.search(line):
                        matches.append(f"{file_path}:{lineno}: {line.rstrip()}")
                        if len(matches) >= max_matches:
                            matches.append(f"\n_(truncated at {max_matches} matches)_")
                            return "\n".join(matches)
        except OSError as e:
            logger.warning("code_grep_read_failed", path=str(file_path), error=str(e))
            continue

    if not matches:
        return f"No matches for pattern '{pattern}' under '{root}' (glob='{glob}', files_scanned={files_scanned})."
    return "\n".join(matches)


@tool(parse_docstring=True)
async def code_read_file(path: str) -> str:
    """Read a text file from the configured code_ops sandbox.

    Use when you need the full source of a single file the user has pointed at
    (or that grep/list_dir surfaced). Binary files are refused; oversized files
    are truncated with a notice — grep instead when you only need a few lines.

    Args:
        path: Absolute or sandbox-relative path to the file.

    Returns:
        The file content wrapped in a fenced markdown block, or an error string.
    """
    resolved = resolve_inside_root(path)
    if resolved is None:
        return (
            f"Error: '{path}' is outside the configured code_ops sandbox. "
            "Ask the user to place the file under one of the allowed roots."
        )
    logger.info("code_read_file_invoked", path=str(resolved))
    return await asyncio.to_thread(_read_file_sync, resolved, settings.CODE_OPS_MAX_READ_BYTES)


@tool(parse_docstring=True)
async def code_list_dir(path: str) -> str:
    """List the contents of a directory inside the code_ops sandbox.

    Use to discover the file/sub-directory layout before reading or grepping.
    Hidden vendored directories (.git, node_modules, .venv, …) are filtered.

    Args:
        path: Absolute or sandbox-relative path to the directory.

    Returns:
        A markdown table of name / kind / size, or an error string.
    """
    resolved = resolve_inside_root(path)
    if resolved is None:
        return (
            f"Error: '{path}' is outside the configured code_ops sandbox. "
            "Ask the user to place the directory under one of the allowed roots."
        )
    logger.info("code_list_dir_invoked", path=str(resolved))
    return await asyncio.to_thread(_list_dir_sync, resolved, settings.CODE_OPS_MAX_LIST_ITEMS)


@tool(parse_docstring=True)
async def code_grep(pattern: str, path: str, glob: str = "*") -> str:
    """Recursively search the sandbox for a regex pattern.

    Prefer this over ``code_read_file`` when you only need to locate where a
    symbol or substring appears. Vendored directories are skipped automatically.

    Args:
        pattern: Python regular expression to search for (case-sensitive).
        path: Absolute or sandbox-relative root to search under.
        glob: Optional rglob filter (e.g. "*.py", "**/*.ts"). Default "*"
            scans every file.

    Returns:
        Newline-separated ``path:line: content`` matches, or a "no match" notice.
    """
    resolved = resolve_inside_root(path)
    if resolved is None:
        return (
            f"Error: '{path}' is outside the configured code_ops sandbox. "
            "Ask the user to place the directory under one of the allowed roots."
        )
    if not resolved.is_dir():
        return f"Error: '{resolved}' is not a directory; grep requires a directory root."
    logger.info("code_grep_invoked", path=str(resolved), pattern=pattern[:80], glob=glob)
    return await asyncio.to_thread(
        _grep_sync,
        pattern,
        resolved,
        glob,
        settings.CODE_OPS_MAX_GREP_MATCHES,
        settings.CODE_OPS_MAX_GREP_FILES,
    )


@tool(parse_docstring=True)
async def code_detect_language(path: str) -> str:
    """Identify the programming language of a file by its extension.

    Use this before deciding which syntax conventions to apply when explaining
    or modifying a file. Returns "unknown" when the extension isn't recognised.

    Args:
        path: Absolute or sandbox-relative path to the file.

    Returns:
        A lowercase language identifier (e.g. ``python``), or ``unknown``.
    """
    resolved = resolve_inside_root(path)
    if resolved is None:
        return (
            f"Error: '{path}' is outside the configured code_ops sandbox. "
            "Ask the user to place the file under one of the allowed roots."
        )
    suffix = resolved.suffix.lower()
    if resolved.name.lower() == "dockerfile":
        return "dockerfile"
    if resolved.name.lower() == "makefile":
        return "makefile"
    return _LANG_BY_EXT.get(suffix, "unknown")
