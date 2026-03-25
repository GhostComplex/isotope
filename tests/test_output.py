"""Tests for TUI output module — markdown rendering and styled printing."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from isotope_agents.tui.output import (
    HAS_RICH,
    StreamBuffer,
    get_terminal_width,
    render_markdown,
    tui_print,
    tui_print_inline,
)


class TestTuiPrint:
    """Tests for tui_print and tui_print_inline."""

    def test_print_plain_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        tui_print("hello world")
        captured = capsys.readouterr()
        assert "hello world" in captured.out

    def test_print_with_end(self, capsys: pytest.CaptureFixture[str]) -> None:
        tui_print("no newline", end="")
        captured = capsys.readouterr()
        assert captured.out == "no newline" or "no newline" in captured.out

    def test_print_inline(self, capsys: pytest.CaptureFixture[str]) -> None:
        tui_print_inline("inline text")
        captured = capsys.readouterr()
        assert "inline text" in captured.out
        # Should not end with newline (plain mode)
        if not HAS_RICH:
            assert not captured.out.endswith("\n")


class TestRenderMarkdown:
    """Tests for render_markdown."""

    def test_render_empty_string(self, capsys: pytest.CaptureFixture[str]) -> None:
        render_markdown("")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_render_whitespace_only(self, capsys: pytest.CaptureFixture[str]) -> None:
        render_markdown("   \n  \n  ")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_render_plain_text(self, capsys: pytest.CaptureFixture[str]) -> None:
        render_markdown("Hello, world!")
        captured = capsys.readouterr()
        assert "Hello, world!" in captured.out

    def test_render_markdown_heading(self, capsys: pytest.CaptureFixture[str]) -> None:
        render_markdown("# Heading\n\nSome text")
        captured = capsys.readouterr()
        assert "Heading" in captured.out
        assert "Some text" in captured.out

    def test_render_code_block(self, capsys: pytest.CaptureFixture[str]) -> None:
        md = "```python\nprint('hello')\n```"
        render_markdown(md)
        captured = capsys.readouterr()
        assert "print" in captured.out
        assert "hello" in captured.out

    def test_render_bold(self, capsys: pytest.CaptureFixture[str]) -> None:
        render_markdown("This is **bold** text")
        captured = capsys.readouterr()
        assert "bold" in captured.out

    def test_render_list(self, capsys: pytest.CaptureFixture[str]) -> None:
        render_markdown("- item one\n- item two\n- item three")
        captured = capsys.readouterr()
        assert "item one" in captured.out
        assert "item two" in captured.out


class TestStreamBuffer:
    """Tests for StreamBuffer."""

    def test_write_complete_lines(self, capsys: pytest.CaptureFixture[str]) -> None:
        buf = StreamBuffer()
        buf.write("line one\nline two\n")
        captured = capsys.readouterr()
        assert "line one" in captured.out
        assert "line two" in captured.out

    def test_write_partial_line_buffered(self, capsys: pytest.CaptureFixture[str]) -> None:
        buf = StreamBuffer()
        buf.write("partial")
        captured = capsys.readouterr()
        assert captured.out == ""  # Not printed yet

    def test_flush_prints_pending(self, capsys: pytest.CaptureFixture[str]) -> None:
        buf = StreamBuffer()
        buf.write("pending text")
        capsys.readouterr()  # Clear
        buf.flush()
        captured = capsys.readouterr()
        assert "pending text" in captured.out

    def test_drain_returns_pending(self) -> None:
        buf = StreamBuffer()
        buf.write("some text")
        result = buf.drain()
        assert result == "some text"

    def test_drain_clears_buffer(self) -> None:
        buf = StreamBuffer()
        buf.write("data")
        buf.drain()
        assert buf.drain() == ""

    def test_discard_clears_without_printing(self, capsys: pytest.CaptureFixture[str]) -> None:
        buf = StreamBuffer()
        buf.write("secret")
        buf.discard()
        captured = capsys.readouterr()
        assert "secret" not in captured.out
        assert buf.drain() == ""


class TestGetTerminalWidth:
    """Tests for get_terminal_width."""

    def test_returns_int(self) -> None:
        width = get_terminal_width()
        assert isinstance(width, int)
        assert width > 0

    def test_capped_at_120(self) -> None:
        width = get_terminal_width()
        assert width <= 120

    def test_fallback_on_error(self) -> None:
        with patch("os.get_terminal_size", side_effect=OSError):
            width = get_terminal_width()
            assert width == 80
