"""ReadTool — read file contents."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from isotopo_core.tools import Tool, ToolResult


def make_read_tool() -> Tool:
    """Create a tool that reads file contents."""

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Any = None,
    ) -> ToolResult:
        path = params.get("path", "")
        if not path:
            return ToolResult.error("Missing required parameter: path")
        path = os.path.expanduser(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            offset = params.get("offset", 0)
            limit = params.get("limit", 0)

            if offset > 0:
                lines = lines[offset:]
            if limit > 0:
                lines = lines[:limit]

            content = "".join(lines)

            if len(content) > 100_000:
                content = content[:100_000] + f"\n\n... [truncated, {len(content)} chars total]"
            return ToolResult.text(content)
        except FileNotFoundError:
            return ToolResult.error(f"File not found: {path}")
        except PermissionError:
            return ToolResult.error(f"Permission denied: {path}")
        except Exception as e:
            return ToolResult.error(f"Error reading file: {e}")

    return Tool(
        name="read",
        description=(
            "Read the contents of a file at the given path. "
            "Supports offset/limit for large files."
        ),
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative file path to read",
                },
                "offset": {
                    "type": "integer",
                    "description": "Line offset to start reading from (0-based)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of lines to read (0 = all)",
                },
            },
            "required": ["path"],
        },
        execute=_execute,
    )
