"""Tests for extracted file tools (read, write, edit)."""

from __future__ import annotations

import os
import tempfile

import pytest

from isotope_core.tools import Tool


class TestReadFile:
    """Tests for the read_file tool."""

    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    @pytest.fixture(autouse=True)
    def _patch_workspace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import isotope_agents.tools.read as read_mod

        monkeypatch.setattr(read_mod, "_WORKSPACE", self.tmpdir)

    def _get_tool(self) -> Tool:
        from isotope_agents.tools.read import read_file

        return read_file

    @pytest.mark.asyncio
    async def test_read_existing_file(self) -> None:
        path = os.path.join(self.tmpdir, "test.txt")
        with open(path, "w") as f:
            f.write("hello world")
        tool = self._get_tool()
        result = await tool.execute("call_1", {"path": path})
        assert not result.is_error
        assert result.content[0].text == "hello world"

    @pytest.mark.asyncio
    async def test_read_missing_file(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"path": "/nonexistent/file.txt"})
        assert result.is_error
        assert "not found" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_read_relative_path(self) -> None:
        path = os.path.join(self.tmpdir, "relative.txt")
        with open(path, "w") as f:
            f.write("relative content")
        tool = self._get_tool()
        result = await tool.execute("call_1", {"path": "relative.txt"})
        assert not result.is_error
        assert result.content[0].text == "relative content"

    @pytest.mark.asyncio
    async def test_read_truncates_large_file(self) -> None:
        path = os.path.join(self.tmpdir, "large.txt")
        with open(path, "w") as f:
            f.write("x" * 200_000)
        tool = self._get_tool()
        result = await tool.execute("call_1", {"path": path})
        assert not result.is_error
        assert len(result.content[0].text) < 200_000
        assert "truncated" in result.content[0].text


class TestWriteFile:
    """Tests for the write_file tool."""

    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    @pytest.fixture(autouse=True)
    def _patch_workspace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import isotope_agents.tools.read as read_mod

        monkeypatch.setattr(read_mod, "_WORKSPACE", self.tmpdir)

    def _get_tool(self) -> Tool:
        from isotope_agents.tools.write import write_file

        return write_file

    @pytest.mark.asyncio
    async def test_write_new_file(self) -> None:
        tool = self._get_tool()
        path = os.path.join(self.tmpdir, "new.txt")
        result = await tool.execute("call_1", {"path": path, "content": "hello"})
        assert not result.is_error
        with open(path) as f:
            assert f.read() == "hello"

    @pytest.mark.asyncio
    async def test_write_creates_directories(self) -> None:
        tool = self._get_tool()
        path = os.path.join(self.tmpdir, "a", "b", "c.txt")
        result = await tool.execute("call_1", {"path": path, "content": "deep"})
        assert not result.is_error
        with open(path) as f:
            assert f.read() == "deep"

    @pytest.mark.asyncio
    async def test_write_overwrites(self) -> None:
        tool = self._get_tool()
        path = os.path.join(self.tmpdir, "overwrite.txt")
        with open(path, "w") as f:
            f.write("old")
        result = await tool.execute("call_1", {"path": path, "content": "new"})
        assert not result.is_error
        with open(path) as f:
            assert f.read() == "new"


class TestEditFile:
    """Tests for the edit_file tool."""

    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    @pytest.fixture(autouse=True)
    def _patch_workspace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import isotope_agents.tools.read as read_mod

        monkeypatch.setattr(read_mod, "_WORKSPACE", self.tmpdir)

    def _get_tool(self) -> Tool:
        from isotope_agents.tools.edit import edit_file

        return edit_file

    @pytest.mark.asyncio
    async def test_edit_replaces_text(self) -> None:
        path = os.path.join(self.tmpdir, "edit.txt")
        with open(path, "w") as f:
            f.write("Hello, World!")
        tool = self._get_tool()
        result = await tool.execute(
            "call_1",
            {"path": path, "old_text": "World", "new_text": "Python"},
        )
        assert not result.is_error
        with open(path) as f:
            assert f.read() == "Hello, Python!"

    @pytest.mark.asyncio
    async def test_edit_not_found(self) -> None:
        path = os.path.join(self.tmpdir, "edit2.txt")
        with open(path, "w") as f:
            f.write("Hello")
        tool = self._get_tool()
        result = await tool.execute(
            "call_1",
            {"path": path, "old_text": "missing", "new_text": "x"},
        )
        assert result.is_error
        assert "not found" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_edit_multiple_matches(self) -> None:
        path = os.path.join(self.tmpdir, "edit3.txt")
        with open(path, "w") as f:
            f.write("aaa")
        tool = self._get_tool()
        result = await tool.execute(
            "call_1",
            {"path": path, "old_text": "a", "new_text": "b"},
        )
        assert result.is_error
        assert "3 times" in result.content[0].text

    @pytest.mark.asyncio
    async def test_edit_missing_file(self) -> None:
        tool = self._get_tool()
        result = await tool.execute(
            "call_1",
            {"path": "/nonexistent.txt", "old_text": "a", "new_text": "b"},
        )
        assert result.is_error
