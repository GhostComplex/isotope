"""Glob tool for isotopes — find files matching a glob pattern."""

from __future__ import annotations

import os
from pathlib import Path

from isotopes_core.tools import ToolResult, auto_tool

from isotopes.tools import truncate_output

_WORKSPACE = os.getcwd()
MAX_RESULTS = 500


@auto_tool
async def glob_tool(
    pattern: str,
    path: str = ".",
) -> ToolResult:
    """Find files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g. "**/*.py", "src/*.ts").
        path: Base directory to search from.
    """
    if not pattern:
        return ToolResult.error("Missing required parameter: pattern")

    base = os.path.expanduser(path)
    if not os.path.isabs(base):
        base = os.path.join(_WORKSPACE, base)

    base_path = Path(base)
    if not base_path.exists():
        return ToolResult.error(f"Path not found: {base}")

    try:
        matches: list[str] = []
        for match in base_path.glob(pattern):
            # Skip hidden files/dirs
            parts = match.relative_to(base_path).parts
            if any(p.startswith(".") for p in parts):
                continue
            rel = str(match.relative_to(base_path))
            matches.append(rel)
            if len(matches) >= MAX_RESULTS:
                break

        if not matches:
            return ToolResult.text("No files matched the pattern.")

        matches.sort()
        output = "\n".join(matches)
        output = truncate_output(output, max_chars=30_000)
        return ToolResult.text(output)
    except Exception as e:
        return ToolResult.error(f"Error searching: {e}")
