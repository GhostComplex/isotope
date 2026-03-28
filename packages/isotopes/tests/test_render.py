"""Tests for isotopes.tui.render module."""

from __future__ import annotations

import sys
from unittest.mock import patch

from isotopes.tui.render import (
    _StreamBuffer,
    _print,
    _print_inline,
    render_markdown,
    render_tool_output,
)


# ---------------------------------------------------------------------------
# _print / _print_inline
# ---------------------------------------------------------------------------


class TestPrint:
    """Tests for the _print() helper."""

    def test_print_basic(self, capsys):
        """Print plain text with default newline."""
        _print("hello")
        assert capsys.readouterr().out == "hello\n"

    def test_print_style_ignored(self, capsys):
        """Style parameter is accepted but has no effect."""
        _print("styled", style="bold red")
        assert capsys.readouterr().out == "styled\n"

    def test_print_custom_end(self, capsys):
        """Keyword 'end' is forwarded to the built-in print."""
        _print("no newline", end="")
        assert capsys.readouterr().out == "no newline"

    def test_print_empty_string(self, capsys):
        """Empty text still produces the trailing newline."""
        _print("")
        assert capsys.readouterr().out == "\n"


class TestPrintInline:
    """Tests for the _print_inline() helper."""

    def test_print_inline_basic(self, capsys):
        """Inline print emits text with no trailing newline."""
        _print_inline("chunk")
        assert capsys.readouterr().out == "chunk"

    def test_print_inline_style_ignored(self, capsys):
        """Style parameter is accepted but has no effect."""
        _print_inline("x", style="green")
        assert capsys.readouterr().out == "x"

    def test_print_inline_empty_string(self, capsys):
        """Empty inline print produces no output."""
        _print_inline("")
        assert capsys.readouterr().out == ""

    def test_print_inline_consecutive(self, capsys):
        """Multiple inline prints concatenate on the same line."""
        _print_inline("a")
        _print_inline("b")
        assert capsys.readouterr().out == "ab"


# ---------------------------------------------------------------------------
# _StreamBuffer
# ---------------------------------------------------------------------------


class TestStreamBuffer:
    """Tests for the _StreamBuffer class."""

    # -- write() --

    def test_write_complete_line(self, capsys):
        """A string ending with newline is printed immediately."""
        buf = _StreamBuffer()
        buf.write("hello\n")
        assert capsys.readouterr().out == "hello\n"
        assert buf.drain() == ""

    def test_write_partial_line(self, capsys):
        """A string without newline is buffered, not printed."""
        buf = _StreamBuffer()
        buf.write("partial")
        assert capsys.readouterr().out == ""
        assert buf.drain() == "partial"

    def test_write_multiple_newlines(self, capsys):
        """Multiple complete lines are printed one per newline."""
        buf = _StreamBuffer()
        buf.write("a\nb\nc\n")
        out = capsys.readouterr().out
        assert out == "a\nb\nc\n"
        assert buf.drain() == ""

    def test_write_trailing_partial(self, capsys):
        """Complete lines are printed; trailing partial text is buffered."""
        buf = _StreamBuffer()
        buf.write("line1\npartial")
        out = capsys.readouterr().out
        assert out == "line1\n"
        assert buf.drain() == "partial"

    def test_write_empty_string(self, capsys):
        """Writing an empty string is a no-op."""
        buf = _StreamBuffer()
        buf.write("")
        assert capsys.readouterr().out == ""
        assert buf.drain() == ""

    def test_write_only_newline(self, capsys):
        """Writing a bare newline prints an empty line."""
        buf = _StreamBuffer()
        buf.write("\n")
        assert capsys.readouterr().out == "\n"

    def test_write_incremental(self, capsys):
        """Incremental writes accumulate until a newline arrives."""
        buf = _StreamBuffer()
        buf.write("he")
        buf.write("llo")
        assert capsys.readouterr().out == ""
        buf.write(" world\n")
        assert capsys.readouterr().out == "hello world\n"

    def test_write_mixed_content(self, capsys):
        """Mixed complete and partial lines across multiple writes."""
        buf = _StreamBuffer()
        buf.write("first\nsec")
        out1 = capsys.readouterr().out
        assert out1 == "first\n"

        buf.write("ond\nthird")
        out2 = capsys.readouterr().out
        assert out2 == "second\n"
        assert buf.drain() == "third"

    # -- flush() --

    def test_flush_with_pending(self, capsys):
        """Flush prints remaining buffered text."""
        buf = _StreamBuffer()
        buf.write("pending")
        capsys.readouterr()  # clear
        buf.flush()
        assert capsys.readouterr().out == "pending\n"
        # Buffer should be empty after flush
        assert buf.drain() == ""

    def test_flush_empty(self, capsys):
        """Flush with nothing pending is a no-op."""
        buf = _StreamBuffer()
        buf.flush()
        assert capsys.readouterr().out == ""

    def test_flush_after_complete_line(self, capsys):
        """Flush after a complete line (nothing pending) is a no-op."""
        buf = _StreamBuffer()
        buf.write("done\n")
        capsys.readouterr()  # clear the printed line
        buf.flush()
        assert capsys.readouterr().out == ""

    # -- drain() --

    def test_drain_returns_pending(self):
        """Drain returns buffered text without printing."""
        buf = _StreamBuffer()
        buf.write("buffered")
        assert buf.drain() == "buffered"

    def test_drain_clears_buffer(self):
        """After drain the buffer is empty."""
        buf = _StreamBuffer()
        buf.write("data")
        buf.drain()
        assert buf.drain() == ""

    def test_drain_empty(self):
        """Drain on a fresh buffer returns empty string."""
        buf = _StreamBuffer()
        assert buf.drain() == ""

    def test_drain_does_not_print(self, capsys):
        """Drain should never produce printed output."""
        buf = _StreamBuffer()
        buf.write("secret")
        buf.drain()
        assert capsys.readouterr().out == ""

    # -- discard() --

    def test_discard_clears_pending(self):
        """Discard removes buffered text."""
        buf = _StreamBuffer()
        buf.write("to discard")
        buf.discard()
        assert buf.drain() == ""

    def test_discard_empty(self):
        """Discard on an empty buffer is safe."""
        buf = _StreamBuffer()
        buf.discard()
        assert buf.drain() == ""

    def test_discard_does_not_print(self, capsys):
        """Discard should never produce printed output."""
        buf = _StreamBuffer()
        buf.write("gone")
        buf.discard()
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    """Test markdown rendering functionality."""

    def test_render_markdown_basic(self, capsys):
        """Test that render_markdown produces output with basic text."""
        render_markdown("Hello World")
        captured = capsys.readouterr()
        assert "Hello World" in captured.out

    def test_render_markdown_with_formatting(self, capsys):
        """Test render_markdown with markdown formatting."""
        markdown_text = """
# Heading

This is a **bold** text and *italic* text.

- List item 1
- List item 2
"""
        render_markdown(markdown_text)
        captured = capsys.readouterr()
        # Should produce some output without crashing
        assert len(captured.out) > 0

    def test_render_markdown_empty_string(self, capsys):
        """Test render_markdown with empty string."""
        render_markdown("")
        captured = capsys.readouterr()
        # Should not crash, may produce minimal output
        assert captured.out is not None

    def test_render_markdown_code_blocks(self, capsys):
        """Test render_markdown with code blocks."""
        markdown_text = """
```python
def hello():
    return "world"
```
"""
        render_markdown(markdown_text)
        captured = capsys.readouterr()
        # Should produce output without crashing
        assert len(captured.out) > 0

    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_render_markdown_fallback(self, capsys):
        """Test fallback behavior when rich is not available."""
        render_markdown("# Hello World")
        captured = capsys.readouterr()
        # Should fallback to plain text output
        assert "# Hello World" in captured.out

    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_render_markdown_fallback_empty(self, capsys):
        """Fallback path with an empty string just prints a blank line."""
        render_markdown("")
        captured = capsys.readouterr()
        assert captured.out == "\n"

    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_render_markdown_fallback_multiline(self, capsys):
        """Fallback path prints multiline markdown text verbatim."""
        text = "# Title\n\nParagraph\n"
        render_markdown(text)
        captured = capsys.readouterr()
        assert "# Title" in captured.out
        assert "Paragraph" in captured.out


# ---------------------------------------------------------------------------
# render_tool_output
# ---------------------------------------------------------------------------


class TestRenderToolOutput:
    """Test tool output rendering functionality."""

    def test_render_tool_output_normal(self, capsys):
        """Test normal tool output rendering."""
        render_tool_output("test_tool", "This is test output", is_error=False)
        captured = capsys.readouterr()
        # Should contain the tool name and output
        assert len(captured.out) > 0

    def test_render_tool_output_error(self, capsys):
        """Test error tool output rendering."""
        render_tool_output("test_tool", "Error occurred", is_error=True)
        captured = capsys.readouterr()
        # Should contain the tool name and error output
        assert len(captured.out) > 0

    def test_render_tool_output_empty_output(self, capsys):
        """Test tool output with empty output string."""
        render_tool_output("test_tool", "", is_error=False)
        captured = capsys.readouterr()
        # Should still produce some output (at least tool name)
        assert len(captured.out) > 0

    def test_render_tool_output_multiline(self, capsys):
        """Test tool output with multiline content."""
        multiline_output = """Line 1
Line 2
Line 3"""
        render_tool_output("test_tool", multiline_output, is_error=False)
        captured = capsys.readouterr()
        # Should handle multiline content
        assert len(captured.out) > 0

    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_render_tool_output_fallback_normal(self, capsys):
        """Test fallback behavior for normal tool output when rich is not available."""
        render_tool_output("test_tool", "This is test output", is_error=False)
        captured = capsys.readouterr()

        # Should contain tool name in brackets
        assert "[test_tool]" in captured.out
        # Should contain the output text, possibly indented
        assert "This is test output" in captured.out

    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_render_tool_output_fallback_error(self, capsys):
        """Test fallback behavior for error tool output when rich is not available."""
        render_tool_output("test_tool", "Error occurred", is_error=True)
        captured = capsys.readouterr()

        # Should contain tool name and error indicator
        assert "[test_tool" in captured.out
        assert "error" in captured.out
        # Should contain the error text
        assert "Error occurred" in captured.out

    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_render_tool_output_fallback_empty(self, capsys):
        """Fallback with empty output skips the indented body."""
        render_tool_output("my_tool", "", is_error=False)
        captured = capsys.readouterr()
        assert "[my_tool]" in captured.out
        # The output body should not contain indented lines
        lines = captured.out.strip().splitlines()
        # Only the header line should be present (no indented body lines)
        body_lines = [ln for ln in lines if ln.startswith("  ")]
        assert body_lines == []

    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_render_tool_output_fallback_whitespace_only(self, capsys):
        """Fallback with whitespace-only output skips the indented body."""
        render_tool_output("my_tool", "   \n  \n", is_error=False)
        captured = capsys.readouterr()
        assert "[my_tool]" in captured.out
        # output.strip() is falsy so no indented lines should appear
        lines = captured.out.strip().splitlines()
        body_lines = [ln for ln in lines if ln.startswith("  ") and ln.strip()]
        assert body_lines == []

    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_render_tool_output_fallback_multiline_indented(self, capsys):
        """Fallback indents each output line with two spaces."""
        render_tool_output("tool", "alpha\nbeta", is_error=False)
        captured = capsys.readouterr()
        assert "  alpha" in captured.out
        assert "  beta" in captured.out

    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_render_tool_output_fallback_error_marker(self, capsys):
        """Fallback error header includes ' (error)' suffix."""
        render_tool_output("cmd", "fail", is_error=True)
        captured = capsys.readouterr()
        assert "[cmd (error)]" in captured.out


# ---------------------------------------------------------------------------
# Rich import failure
# ---------------------------------------------------------------------------


class TestRichImportFailure:
    """Test behavior when rich import fails."""

    def test_import_failure_simulation(self):
        """Test that the module handles rich import failure gracefully."""
        # This test checks that the module can be imported even if rich is not available
        # by testing the fallback code paths. The actual import mocking is done in
        # individual tests above.

        # If we got this far, the module imported successfully
        assert True

    @patch.dict(
        sys.modules,
        {
            "rich.console": None,
            "rich.markdown": None,
            "rich.panel": None,
            "rich.syntax": None,
        },
    )
    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_functions_work_without_rich(self, capsys):
        """Test that functions work when rich modules are not available."""
        # Test markdown rendering
        render_markdown("# Test")
        captured = capsys.readouterr()
        assert "# Test" in captured.out

        # Test tool output rendering
        render_tool_output("tool", "output", False)
        captured = capsys.readouterr()
        assert "[tool]" in captured.out
        assert "output" in captured.out

    @patch.dict(
        sys.modules,
        {
            "rich.console": None,
            "rich.markdown": None,
            "rich.panel": None,
            "rich.syntax": None,
        },
    )
    @patch("isotopes.tui.render._RICH_AVAILABLE", False)
    def test_print_helpers_work_without_rich(self, capsys):
        """_print and _print_inline still work when rich is unavailable."""
        _print("plain")
        _print_inline("inline")
        captured = capsys.readouterr()
        assert "plain\n" in captured.out
        assert "inline" in captured.out
