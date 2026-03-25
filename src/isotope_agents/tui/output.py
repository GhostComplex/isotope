"""Output helpers for the isotope-agents TUI.

Provides print utilities and a stream buffer for rendering output
above the prompt-toolkit input prompt.
"""

from __future__ import annotations

from typing import Any


def tui_print(text: str, style: str | None = None, **kw: Any) -> None:
    """Print text to stdout.

    Args:
        text: Text to print.
        style: Style hint (currently unused, reserved for rich rendering).
        **kw: Additional kwargs passed to print() (e.g. end="").
    """
    del style
    print(text, end=kw.get("end", "\n"))


def tui_print_inline(text: str, style: str | None = None) -> None:
    """Print text inline (no newline).

    Args:
        text: Text to print.
        style: Style hint (currently unused).
    """
    del style
    print(text, end="", flush=True)


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
