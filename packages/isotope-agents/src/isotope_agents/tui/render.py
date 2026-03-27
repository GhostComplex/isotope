"""Output rendering helpers for isotope-agents TUI.

This module provides output formatting utilities, stream buffering for prompt_toolkit
integration, and styled console output functions.
"""

from __future__ import annotations

from typing import Any

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.text import Text
    _RICH_AVAILABLE = True
except ImportError:
    _RICH_AVAILABLE = False


# ---------------------------------------------------------------------------
# Output helpers (plain stdout)
# ---------------------------------------------------------------------------

def _print(text: str, style: str | None = None, **kw: Any) -> None:
    """Print text with optional style (styles ignored in plain mode)."""
    del style
    print(text, end=kw.get("end", "\n"))


def _print_inline(text: str, style: str | None = None) -> None:
    """Print text inline without newline (styles ignored in plain mode)."""
    del style
    print(text, end="", flush=True)


# ---------------------------------------------------------------------------
# Stream buffer for prompt_toolkit integration
# ---------------------------------------------------------------------------

class _StreamBuffer:
    """Buffer streaming text, print complete lines only.

    When prompt_toolkit is active, streaming output must be printed as complete
    lines for patch_stdout to render them correctly above the prompt.
    This helper buffers partial deltas and flushes only on newline boundaries.
    """

    def __init__(self) -> None:
        self._pending = ""

    def write(self, text: str) -> None:
        """Buffer text. Immediately print each complete line."""
        self._pending += text
        while "\n" in self._pending:
            line, self._pending = self._pending.split("\n", 1)
            print(line)

    def flush(self) -> None:
        """Print any remaining buffered text."""
        if self._pending:
            print(self._pending)
            self._pending = ""

    def drain(self) -> str:
        """Return buffered text and clear it without printing."""
        pending = self._pending
        self._pending = ""
        return pending

    def discard(self) -> None:
        """Discard buffered text without printing (used on cancellation)."""
        self._pending = ""


# ---------------------------------------------------------------------------
# Rich markdown rendering (with fallback)
# ---------------------------------------------------------------------------

def render_markdown(text: str) -> None:
    """Render text as markdown using Rich if available, otherwise plain text.

    Args:
        text: The markdown text to render.
    """
    if _RICH_AVAILABLE:
        console = Console()
        markdown = Markdown(text)
        console.print(markdown)
    else:
        # Fallback to plain text
        print(text)


def render_tool_output(tool_name: str, output: str, is_error: bool = False) -> None:
    """Render tool output in a panel using Rich if available.

    Args:
        tool_name: Name of the tool that produced the output.
        output: The tool output text.
        is_error: Whether this is error output.
    """
    if _RICH_AVAILABLE:
        console = Console()
        style = "red" if is_error else "blue"
        title = f"[{style}]{tool_name}[/{style}]" + (" (error)" if is_error else "")
        text = Text.from_ansi(output)
        panel = Panel(text, title=title, border_style=style)
        console.print(panel)
    else:
        # Fallback to plain text
        error_marker = " (error)" if is_error else ""
        print(f"\n[{tool_name}{error_marker}]")
        if output.strip():
            # Indent the output slightly for visual separation
            for line in output.splitlines():
                print(f"  {line}")
        print()
