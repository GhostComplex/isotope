"""GlobTool — list files matching glob patterns.

Uses Python's pathlib.Path.glob() for cross-platform file discovery.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from isotopo_core.tools import Tool, ToolResult


def make_glob_tool() -> Tool:
    """Create a GlobTool for listing files matching glob patterns.

    Returns:
        A Tool instance for glob-based file discovery.
    """

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Any = None,
    ) -> ToolResult:
        pattern = params.get("pattern", "")
        if not pattern:
            return ToolResult.error("Missing required parameter: pattern")

        base_path = Path(params.get("path", ".")).expanduser().resolve()

        if not base_path.exists():
            return ToolResult.error(f"Path does not exist: {base_path}")
        if not base_path.is_dir():
            return ToolResult.error(f"Path is not a directory: {base_path}")

        try:
            # Run glob in executor to avoid blocking the event loop on large trees
            loop = asyncio.get_running_loop()
            matches = await loop.run_in_executor(
                None, lambda: sorted(str(p) for p in base_path.glob(pattern) if not p.is_dir())
            )

            if not matches:
                return ToolResult.text("No files matched the pattern.")

            # Cap results to prevent huge output
            max_results = 200
            truncated = len(matches) > max_results
            result_lines = matches[:max_results]

            output = "\n".join(result_lines)
            if truncated:
                output += f"\n\n... [{len(matches)} total matches, showing first {max_results}]"

            return ToolResult.text(output)
        except Exception as e:
            return ToolResult.error(f"Error running glob: {e}")

    return Tool(
        name="glob",
        description=(
            "List files matching a glob pattern. "
            "Supports recursive patterns like '**/*.py'. "
            "Returns a list of matching file paths."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match (e.g. '**/*.py', 'src/**/*.ts')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search in (default: current directory)",
                },
            },
            "required": ["pattern"],
        },
        execute=_execute,
    )
