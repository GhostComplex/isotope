"""BashTool — execute shell commands via subprocess."""

from __future__ import annotations

import asyncio
from typing import Any

from isotope_core.tools import Tool, ToolResult


def make_bash_tool() -> Tool:
    """Create a bash/terminal tool that runs shell commands."""

    async def _execute(
        tool_call_id: str,
        params: dict[str, Any],
        signal: asyncio.Event | None = None,
        on_update: Any = None,
    ) -> ToolResult:
        command = params.get("command", "")
        if not command:
            return ToolResult.error("Missing required parameter: command")
        timeout = min(params.get("timeout", 30), 120)  # cap at 120s
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except TimeoutError:
                proc.kill()
                return ToolResult.error(f"Command timed out after {timeout}s")
            output = stdout.decode("utf-8", errors="replace") if stdout else ""
            if len(output) > 50_000:
                output = output[:50_000] + f"\n\n... [truncated, {len(output)} chars total]"
            exit_code = proc.returncode
            result = f"Exit code: {exit_code}\n{output}" if output else f"Exit code: {exit_code}"
            if exit_code != 0:
                return ToolResult.error(result)
            return ToolResult.text(result)
        except Exception as e:
            return ToolResult.error(f"Error running command: {e}")

    return Tool(
        name="bash",
        description=(
            "Execute a shell command and return stdout/stderr. "
            "Timeout defaults to 30s, max 120s."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds (default 30, max 120)",
                },
            },
            "required": ["command"],
        },
        execute=_execute,
    )
