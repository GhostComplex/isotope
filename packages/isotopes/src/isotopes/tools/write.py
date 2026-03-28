"""Write file tool for isotopes."""

from __future__ import annotations

import os

from isotopes_core.tools import ToolResult, auto_tool

from isotopes.tools.read import _resolve_path


@auto_tool
async def write_file(path: str, content: str) -> ToolResult:
    """Create or overwrite a file with the given content. Creates parent directories if needed.

    Args:
        path: Absolute or relative file path to write.
        content: Content to write to the file.
    """
    if not path:
        return ToolResult.error("Missing required parameter: path")
    resolved = _resolve_path(path)
    try:
        os.makedirs(os.path.dirname(resolved) or ".", exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolResult.text(f"Written {len(content)} chars to {resolved}")
    except PermissionError:
        return ToolResult.error(f"Permission denied: {resolved}")
    except Exception as e:
        return ToolResult.error(f"Error writing file: {e}")
