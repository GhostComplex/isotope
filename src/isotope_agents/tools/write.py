"""WriteTool — create or overwrite files."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from isotopo_core.tools import Tool, ToolResult


def make_write_tool() -> Tool:
    """Create a tool that writes content to files."""

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Any = None,
    ) -> ToolResult:
        path = params.get("path", "")
        content = params.get("content", "")
        if not path:
            return ToolResult.error("Missing required parameter: path")
        path = os.path.expanduser(path)
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return ToolResult.text(f"Written {len(content)} chars to {path}")
        except PermissionError:
            return ToolResult.error(f"Permission denied: {path}")
        except Exception as e:
            return ToolResult.error(f"Error writing file: {e}")

    return Tool(
        name="write",
        description=(
            "Create or overwrite a file with the given content. "
            "Creates parent directories if needed."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
        execute=_execute,
    )
