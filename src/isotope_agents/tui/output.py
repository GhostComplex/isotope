"""Output helpers for the isotope-agents TUI.

Provides print utilities, a stream buffer for rendering output
above the prompt-toolkit input prompt, and rich markdown rendering.
"""

from __future__ import annotations

import os
from typing import Any

# ---------------------------------------------------------------------------
# Optional rich support
# ---------------------------------------------------------------------------

try:
    from rich.console import Console as _Console
    from rich.markdown import Markdown as _Markdown
    from rich.theme import Theme as _Theme

    _ISOTOPE_THEME = _Theme(
        {
            "info": "cyan",
            "dim": "dim",
            "warn": "yellow",
            "err": "bold red",
            "tool": "green",
            "model": "white",
            "user": "bold blue",
        }
    )

    _console = _Console(theme=_ISOTOPE_THEME, highlight=False)
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    _console = None  # type: ignore[assignment]


def tui_print(text: str, style: str | None = None, **kw: Any) -> None:
    """Print text to stdout, optionally styled with rich.

    Args:
        text: Text to print.
        style: Style name from the isotope theme (info, dim, warn, err, tool, model, user).
        **kw: Additional kwargs passed to print() (e.g. end="").
    """
    if HAS_RICH and _console is not None and style:
        end = kw.get("end", "\n")
        _console.print(text, style=style, end=end, highlight=False)
    else:
        print(text, end=kw.get("end", "\n"))


def tui_print_inline(text: str, style: str | None = None) -> None:
    """Print text inline (no newline).

    Args:
        text: Text to print.
        style: Style name from the isotope theme.
    """
    if HAS_RICH and _console is not None and style:
        _console.print(text, style=style, end="", highlight=False)
    else:
        print(text, end="", flush=True)


def render_markdown(text: str) -> None:
    """Render text as markdown using rich.

    Falls back to plain text if rich is not installed.
    Code blocks get syntax highlighting automatically via rich.

    Args:
        text: Markdown-formatted text to render.
    """
    if not text.strip():
        return

    if HAS_RICH and _console is not None:
        width = get_terminal_width()
        md = _Markdown(text)
        _console.print(md, width=width)
    else:
        print(text)


def get_terminal_width() -> int:
    """Get terminal width, capped at 120 columns."""
    try:
        return min(os.get_terminal_size().columns, 120)
    except OSError:
        return 80


class StreamBuffer:
    """Buffer streaming text, print complete lines only.

    When prompt_toolkit is active, streaming output must be printed as
    complete lines for patch_stdout to render them correctly above the prompt.
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
