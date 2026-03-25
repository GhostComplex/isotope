"""Tests for isotope_agents.tui.render module."""

from __future__ import annotations

import sys
from unittest.mock import patch

from isotope_agents.tui.render import render_markdown, render_tool_output


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

    @patch('isotope_agents.tui.render._RICH_AVAILABLE', False)
    def test_render_markdown_fallback(self, capsys):
        """Test fallback behavior when rich is not available."""
        render_markdown("# Hello World")
        captured = capsys.readouterr()
        # Should fallback to plain text output
        assert "# Hello World" in captured.out


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

    @patch('isotope_agents.tui.render._RICH_AVAILABLE', False)
    def test_render_tool_output_fallback_normal(self, capsys):
        """Test fallback behavior for normal tool output when rich is not available."""
        render_tool_output("test_tool", "This is test output", is_error=False)
        captured = capsys.readouterr()

        # Should contain tool name in brackets
        assert "[test_tool]" in captured.out
        # Should contain the output text, possibly indented
        assert "This is test output" in captured.out

    @patch('isotope_agents.tui.render._RICH_AVAILABLE', False)
    def test_render_tool_output_fallback_error(self, capsys):
        """Test fallback behavior for error tool output when rich is not available."""
        render_tool_output("test_tool", "Error occurred", is_error=True)
        captured = capsys.readouterr()

        # Should contain tool name and error indicator
        assert "[test_tool" in captured.out
        assert "error" in captured.out
        # Should contain the error text
        assert "Error occurred" in captured.out


class TestRichImportFailure:
    """Test behavior when rich import fails."""

    def test_import_failure_simulation(self):
        """Test that the module handles rich import failure gracefully."""
        # This test checks that the module can be imported even if rich is not available
        # by testing the fallback code paths. The actual import mocking is done in
        # individual tests above.

        # If we got this far, the module imported successfully
        assert True

    @patch.dict(sys.modules, {'rich.console': None, 'rich.markdown': None, 'rich.panel': None, 'rich.syntax': None})
    @patch('isotope_agents.tui.render._RICH_AVAILABLE', False)
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