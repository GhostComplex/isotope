"""Edit file tool for isotope-agents."""

from __future__ import annotations

from isotope_core.tools import ToolResult, auto_tool

from isotope_agents.tools.read import _resolve_path


@auto_tool
async def edit_file(path: str, old_text: str, new_text: str) -> ToolResult:
    """Edit a file by replacing an exact text match. old_text must match exactly once.

    Args:
        path: Absolute or relative file path to edit.
        old_text: Exact text to find (must match exactly once).
        new_text: Text to replace old_text with.
    """
    if not path:
        return ToolResult.error("Missing required parameter: path")
    if not old_text:
        return ToolResult.error("Missing required parameter: old_text")
    resolved = _resolve_path(path)
    try:
        with open(resolved, encoding="utf-8") as f:
            content = f.read()
        count = content.count(old_text)
        if count == 0:
            return ToolResult.error(
                f"old_text not found in {resolved}. Make sure it matches exactly."
            )
        if count > 1:
            return ToolResult.error(
                f"old_text found {count} times in {resolved}. Must match exactly once."
            )
        content = content.replace(old_text, new_text, 1)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)
        return ToolResult.text(f"Edited {resolved}: replaced 1 occurrence")
    except FileNotFoundError:
        return ToolResult.error(f"File not found: {resolved}")
    except PermissionError:
        return ToolResult.error(f"Permission denied: {resolved}")
    except Exception as e:
        return ToolResult.error(f"Error editing file: {e}")
