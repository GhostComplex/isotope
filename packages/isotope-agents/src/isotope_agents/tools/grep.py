"""Grep tool for isotope-agents — search files using ripgrep or Python fallback."""

from __future__ import annotations

import asyncio
import os
import re

from isotope_core.tools import ToolResult, auto_tool

from isotope_agents.tools import truncate_output

_WORKSPACE = os.getcwd()
MAX_RESULTS = 100


def _resolve_path(path: str) -> str:
    """Resolve to absolute path against workspace."""
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(_WORKSPACE, path)
    return path


async def _rg_search(
    pattern: str,
    path: str,
    include: str | None,
    max_results: int,
) -> str | None:
    """Try ripgrep. Returns output string or None if rg not available."""
    cmd = ["rg", "--line-number", "--no-heading", "--color=never"]
    cmd += ["--max-count", str(max_results)]
    if include:
        cmd += ["--glob", include]
    cmd += [pattern, path]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace")
        if proc.returncode == 1:
            return ""  # no matches
        # rg error
        return None
    except FileNotFoundError:
        return None
    except TimeoutError:
        if proc is not None:
            proc.kill()
            await proc.wait()
        return None


def _python_search(
    pattern: str,
    path: str,
    include: str | None,
    max_results: int,
) -> str:
    """Fallback: search with Python re + os.walk."""
    import fnmatch

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Invalid regex pattern: {e}"

    results: list[str] = []
    for root, _dirs, files in os.walk(path):
        # Skip hidden directories
        _dirs[:] = [d for d in _dirs if not d.startswith(".")]
        for fname in files:
            if include and not fnmatch.fnmatch(fname, include):
                continue
            filepath = os.path.join(root, fname)
            rel_path = os.path.relpath(filepath, path)
            try:
                with open(filepath, encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if regex.search(line):
                            results.append(f"{rel_path}:{lineno}:{line.rstrip()}")
                            if len(results) >= max_results:
                                return "\n".join(results)
            except (PermissionError, OSError):
                continue
    return "\n".join(results)


@auto_tool
async def grep(
    pattern: str,
    path: str = ".",
    include: str | None = None,
    max_results: int = MAX_RESULTS,
) -> ToolResult:
    """Search for a regex pattern in files using ripgrep (or Python fallback).

    Args:
        pattern: Regex pattern to search for.
        path: Directory to search in.
        include: Glob pattern to filter files (e.g. "*.py").
        max_results: Maximum number of matching lines to return.
    """
    if not pattern:
        return ToolResult.error("Missing required parameter: pattern")

    resolved = _resolve_path(path)
    if not os.path.exists(resolved):
        return ToolResult.error(f"Path not found: {resolved}")

    # Try ripgrep first
    rg_result = await _rg_search(pattern, resolved, include, max_results)
    if rg_result is not None:
        output = rg_result
    else:
        output = _python_search(pattern, resolved, include, max_results)

    if not output:
        return ToolResult.text("No matches found.")

    output = truncate_output(output, max_chars=30_000)
    return ToolResult.text(output)
