"""Tests for isotope-agents tools."""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from isotope_agents.tools import TOOL_FACTORIES, get_tool, get_tools
from isotope_agents.tools.bash import make_bash_tool
from isotope_agents.tools.edit import make_edit_tool
from isotope_agents.tools.glob import make_glob_tool
from isotope_agents.tools.grep import make_grep_tool
from isotope_agents.tools.read import make_read_tool
from isotope_agents.tools.write import make_write_tool


# =========================================================================
# Tool instantiation and schema tests
# =========================================================================


class TestToolInstantiation:
    """Test that all tools can be instantiated and have correct schemas."""

    def test_all_tools_registered(self) -> None:
        """All expected tool names are in the registry."""
        expected = {"bash", "read", "write", "edit", "grep", "glob"}
        assert set(TOOL_FACTORIES.keys()) == expected

    @pytest.mark.parametrize("name", list(TOOL_FACTORIES.keys()))
    def test_tool_has_name(self, name: str) -> None:
        """Each tool has a matching name attribute."""
        tool = get_tool(name)
        assert tool.name == name

    @pytest.mark.parametrize("name", list(TOOL_FACTORIES.keys()))
    def test_tool_has_description(self, name: str) -> None:
        """Each tool has a non-empty description."""
        tool = get_tool(name)
        assert tool.description
        assert len(tool.description) > 10

    @pytest.mark.parametrize("name", list(TOOL_FACTORIES.keys()))
    def test_tool_has_parameters_schema(self, name: str) -> None:
        """Each tool has a valid JSON schema for parameters."""
        tool = get_tool(name)
        assert tool.parameters["type"] == "object"
        assert "properties" in tool.parameters

    @pytest.mark.parametrize("name", list(TOOL_FACTORIES.keys()))
    def test_tool_to_schema(self, name: str) -> None:
        """Each tool can produce a schema dict for LLM APIs."""
        tool = get_tool(name)
        schema = tool.to_schema()
        assert schema["name"] == name
        assert "description" in schema
        assert "parameters" in schema

    def test_get_tools_multiple(self) -> None:
        """get_tools returns multiple tools in order."""
        tools = get_tools(["bash", "read", "write"])
        assert len(tools) == 3
        assert tools[0].name == "bash"
        assert tools[1].name == "read"
        assert tools[2].name == "write"

    def test_get_tool_unknown_raises(self) -> None:
        """get_tool raises KeyError for unknown names."""
        with pytest.raises(KeyError, match="Unknown tool"):
            get_tool("nonexistent")


# =========================================================================
# Tool execution tests
# =========================================================================


class TestBashTool:
    """Test BashTool execution."""

    @pytest.mark.asyncio
    async def test_echo(self) -> None:
        tool = make_bash_tool()
        result = await tool.execute("test-id", {"command": "echo hello"})
        assert not result.is_error
        assert "hello" in result.content[0].text

    @pytest.mark.asyncio
    async def test_missing_command(self) -> None:
        tool = make_bash_tool()
        result = await tool.execute("test-id", {"command": ""})
        assert result.is_error
        assert "Missing required" in result.content[0].text

    @pytest.mark.asyncio
    async def test_nonzero_exit(self) -> None:
        tool = make_bash_tool()
        result = await tool.execute("test-id", {"command": "exit 1"})
        assert result.is_error
        assert "Exit code: 1" in result.content[0].text


class TestReadTool:
    """Test ReadTool execution."""

    @pytest.mark.asyncio
    async def test_read_file(self) -> None:
        tool = make_read_tool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("line 1\nline 2\nline 3\n")
            path = f.name

        try:
            result = await tool.execute("test-id", {"path": path})
            assert not result.is_error
            assert "line 1" in result.content[0].text
            assert "line 3" in result.content[0].text
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_read_with_offset_and_limit(self) -> None:
        tool = make_read_tool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("line 0\nline 1\nline 2\nline 3\nline 4\n")
            path = f.name

        try:
            result = await tool.execute("test-id", {"path": path, "offset": 1, "limit": 2})
            assert not result.is_error
            text = result.content[0].text
            assert "line 1" in text
            assert "line 2" in text
            assert "line 0" not in text
            assert "line 3" not in text
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_read_missing_file(self) -> None:
        tool = make_read_tool()
        result = await tool.execute("test-id", {"path": "/nonexistent/file.txt"})
        assert result.is_error
        assert "not found" in result.content[0].text.lower()


class TestWriteTool:
    """Test WriteTool execution."""

    @pytest.mark.asyncio
    async def test_write_file(self) -> None:
        tool = make_write_tool()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            result = await tool.execute("test-id", {"path": path, "content": "hello world"})
            assert not result.is_error
            assert "Written" in result.content[0].text

            with open(path) as f:
                assert f.read() == "hello world"

    @pytest.mark.asyncio
    async def test_write_creates_parents(self) -> None:
        tool = make_write_tool()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "sub", "dir", "test.txt")
            result = await tool.execute("test-id", {"path": path, "content": "nested"})
            assert not result.is_error
            assert os.path.exists(path)


class TestEditTool:
    """Test EditTool execution."""

    @pytest.mark.asyncio
    async def test_edit_file(self) -> None:
        tool = make_edit_tool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            path = f.name

        try:
            result = await tool.execute(
                "test-id",
                {"path": path, "old_text": "hello", "new_text": "goodbye"},
            )
            assert not result.is_error
            with open(path) as f:
                assert f.read() == "goodbye world"
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_edit_not_found(self) -> None:
        tool = make_edit_tool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello world")
            path = f.name

        try:
            result = await tool.execute(
                "test-id",
                {"path": path, "old_text": "nonexistent", "new_text": "x"},
            )
            assert result.is_error
            assert "not found" in result.content[0].text.lower()
        finally:
            os.unlink(path)

    @pytest.mark.asyncio
    async def test_edit_multiple_matches(self) -> None:
        tool = make_edit_tool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello hello")
            path = f.name

        try:
            result = await tool.execute(
                "test-id",
                {"path": path, "old_text": "hello", "new_text": "x"},
            )
            assert result.is_error
            assert "2 times" in result.content[0].text
        finally:
            os.unlink(path)


class TestGrepTool:
    """Test GrepTool execution."""

    @pytest.mark.asyncio
    async def test_grep_finds_pattern(self) -> None:
        tool = make_grep_tool()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w") as f:
                f.write("foo bar\nbaz qux\nfoo again\n")

            result = await tool.execute("test-id", {"pattern": "foo", "path": tmpdir})
            assert not result.is_error
            assert "foo" in result.content[0].text

    @pytest.mark.asyncio
    async def test_grep_no_matches(self) -> None:
        tool = make_grep_tool()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            with open(path, "w") as f:
                f.write("hello world\n")

            result = await tool.execute("test-id", {"pattern": "nonexistent", "path": tmpdir})
            assert not result.is_error
            assert "No matches" in result.content[0].text


class TestGlobTool:
    """Test GlobTool execution."""

    @pytest.mark.asyncio
    async def test_glob_finds_files(self) -> None:
        tool = make_glob_tool()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some test files
            for name in ["a.py", "b.py", "c.txt"]:
                with open(os.path.join(tmpdir, name), "w") as f:
                    f.write("content")

            result = await tool.execute("test-id", {"pattern": "*.py", "path": tmpdir})
            assert not result.is_error
            text = result.content[0].text
            assert "a.py" in text
            assert "b.py" in text
            assert "c.txt" not in text

    @pytest.mark.asyncio
    async def test_glob_no_matches(self) -> None:
        tool = make_glob_tool()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await tool.execute("test-id", {"pattern": "*.xyz", "path": tmpdir})
            assert not result.is_error
            assert "No files" in result.content[0].text

    @pytest.mark.asyncio
    async def test_glob_recursive(self) -> None:
        tool = make_glob_tool()
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "sub")
            os.makedirs(subdir)
            with open(os.path.join(subdir, "nested.py"), "w") as f:
                f.write("content")

            result = await tool.execute("test-id", {"pattern": "**/*.py", "path": tmpdir})
            assert not result.is_error
            assert "nested.py" in result.content[0].text
