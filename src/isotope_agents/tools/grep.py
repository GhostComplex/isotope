"""GrepTool — search file contents using regex patterns.

Uses ripgrep (rg) if available, falls back to grep -rn.
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

from isotope_core.tools import Tool, ToolResult


def make_grep_tool() -> Tool:
    """Create a GrepTool for searching file contents with regex.

    Returns:
        A Tool instance for regex-based content search.
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

        path = params.get("path", ".")
        include = params.get("include", "")
        max_results = params.get("max_results", 50)

        # Build command: prefer rg, fall back to grep
        rg_path = shutil.which("rg")
        if rg_path:
            cmd_parts = [rg_path, "--no-heading", "--line-number", "--color=never"]
            if include:
                cmd_parts.extend(["--glob", include])
            cmd_parts.extend(["-m", str(max_results), "--", pattern, path])
        else:
            cmd_parts = ["grep", "-rn", "--color=never"]
            if include:
                cmd_parts.extend(["--include", include])
            cmd_parts.extend(["-m", str(max_results), "--", pattern, path])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            except TimeoutError:
                proc.kill()
                return ToolResult.error("Search timed out after 30s")

            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            err_output = stderr.decode("utf-8", errors="replace") if stderr else ""

            if proc.returncode == 1:
                # No matches found (normal for grep/rg)
                return ToolResult.text("No matches found.")

            if proc.returncode not in (0, 1):
                return ToolResult.error(f"Search failed: {err_output or 'unknown error'}")

            if not output.strip():
                return ToolResult.text("No matches found.")

            # Truncate very large output
            if len(output) > 50_000:
                output = output[:50_000] + "\n\n... [truncated]"

            return ToolResult.text(output)
        except FileNotFoundError:
            return ToolResult.error(
                "Neither 'rg' (ripgrep) nor 'grep' found on this system."
            )
        except Exception as e:
            return ToolResult.error(f"Error running search: {e}")

    return Tool(
        name="grep",
        description=(
            "Search file contents using regex patterns. "
            "Uses ripgrep (rg) if available, falls back to grep. "
            "Returns matching lines with file:line format."
        ),
        parameters={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in (default: current directory)",
                },
                "include": {
                    "type": "string",
                    "description": "File glob pattern to filter (e.g. '*.py', '*.ts')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matching lines per file (default: 50)",
                },
            },
            "required": ["pattern"],
        },
        execute=_execute,
    )
