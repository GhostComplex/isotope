"""Bash/terminal tool for isotope-agents."""

from __future__ import annotations

import asyncio
import os

from isotope_core.tools import ToolResult, auto_tool

from isotope_agents.tools import truncate_output

# Default workspace for command execution.
_WORKSPACE = os.getcwd()

# Limits
DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
MAX_OUTPUT_CHARS = 50_000


@auto_tool
async def bash(command: str, timeout: int = DEFAULT_TIMEOUT) -> ToolResult:
    """Execute a shell command and return stdout/stderr.

    Args:
        command: Shell command to execute.
        timeout: Timeout in seconds (default 30, max 120).
    """
    if not command:
        return ToolResult.error("Missing required parameter: command")
    timeout = min(timeout, MAX_TIMEOUT)
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=_WORKSPACE,
        )
        try:
            stdout, _ = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return ToolResult.error(f"Command timed out after {timeout}s")
        output = stdout.decode("utf-8", errors="replace") if stdout else ""
        output = truncate_output(output, max_chars=MAX_OUTPUT_CHARS, strategy="tail")
        exit_code = proc.returncode
        result = (
            f"Exit code: {exit_code}\n{output}"
            if output
            else f"Exit code: {exit_code}"
        )
        if exit_code != 0:
            return ToolResult.error(result)
        return ToolResult.text(result)
    except Exception as e:
        return ToolResult.error(f"Error running command: {e}")
