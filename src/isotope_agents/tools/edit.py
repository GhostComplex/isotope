"""EditTool — find-and-replace exact text in files.

Lifted from isotope-core TUI's `edit_file` tool.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from isotope_core.tools import Tool, ToolResult


def make_edit_tool() -> Tool:
    """Create an EditTool for exact text replacement in files.

    Returns:
        A Tool instance for editing files via find-and-replace.
    """

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Any = None,
    ) -> ToolResult:
        path = params.get("path", "")
        old_text = params.get("old_text", "")
        new_text = params.get("new_text", "")

        if not path:
            return ToolResult.error("Missing required parameter: path")
        if not old_text:
            return ToolResult.error("Missing required parameter: old_text")

        path = os.path.expanduser(path)

        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()

            count = content.count(old_text)
            if count == 0:
                return ToolResult.error(
                    f"old_text not found in {path}. Make sure it matches exactly."
                )
            if count > 1:
                return ToolResult.error(
                    f"old_text found {count} times in {path}. Must match exactly once."
                )

            content = content.replace(old_text, new_text, 1)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult.text(f"Edited {path}: replaced 1 occurrence")
        except FileNotFoundError:
            return ToolResult.error(f"File not found: {path}")
        except PermissionError:
            return ToolResult.error(f"Permission denied: {path}")
        except Exception as e:
            return ToolResult.error(f"Error editing file: {e}")

    return Tool(
        name="edit",
        description=(
            "Edit a file by replacing an exact text match. "
            "old_text must match exactly once in the file."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path to edit",
                },
                "old_text": {
                    "type": "string",
                    "description": "Exact text to find (must match exactly once)",
                },
                "new_text": {
                    "type": "string",
                    "description": "Text to replace old_text with",
                },
            },
            "required": ["path", "old_text", "new_text"],
        },
        execute=_execute,
    )
