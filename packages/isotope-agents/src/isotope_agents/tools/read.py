"""Read file tool for isotope-agents."""

from __future__ import annotations

import os

from isotope_core.tools import ToolResult, auto_tool

from isotope_agents.tools import truncate_output

# Default workspace — overridden by agent configuration.
_WORKSPACE = os.getcwd()


def _resolve_path(path: str, workspace: str | None = None) -> str:
    """Resolve a tool path to an absolute path."""
    cwd = workspace or _WORKSPACE
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return path


@auto_tool
async def read_file(path: str) -> ToolResult:
    """Read the contents of a file at the given path.

    Args:
        path: Absolute or relative file path to read.
    """
    if not path:
        return ToolResult.error("Missing required parameter: path")
    resolved = _resolve_path(path)
    try:
        with open(resolved, encoding="utf-8", errors="replace") as f:
            content = f.read()
        content = truncate_output(content, max_chars=100_000, strategy="head")
        return ToolResult.text(content)
    except FileNotFoundError:
        return ToolResult.error(f"File not found: {resolved}")
    except PermissionError:
        return ToolResult.error(f"Permission denied: {resolved}")
    except Exception as e:
        return ToolResult.error(f"Error reading file: {e}")
