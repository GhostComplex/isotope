"""Tests for grep tool."""

from __future__ import annotations

import os
import tempfile

import pytest

from isotope_core.tools import Tool


class TestGrepTool:
    """Tests for the grep tool."""

    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        # Create test files
        os.makedirs(os.path.join(self.tmpdir, "src"), exist_ok=True)
        with open(os.path.join(self.tmpdir, "src", "main.py"), "w") as f:
            f.write("def hello():\n    print('world')\n\ndef goodbye():\n    pass\n")
        with open(os.path.join(self.tmpdir, "src", "utils.py"), "w") as f:
            f.write("def helper():\n    return 42\n")
        with open(os.path.join(self.tmpdir, "README.md"), "w") as f:
            f.write("# Hello World\nThis is a test.\n")

    @pytest.fixture(autouse=True)
    def _patch_workspace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import isotope_agents.tools.grep as grep_mod

        monkeypatch.setattr(grep_mod, "_WORKSPACE", self.tmpdir)

    def _get_tool(self) -> Tool:
        from isotope_agents.tools.grep import grep

        return grep

    @pytest.mark.asyncio
    async def test_basic_search(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"pattern": "def", "path": "."})
        assert not result.is_error
        assert "def" in result.content[0].text

    @pytest.mark.asyncio
    async def test_no_matches(self) -> None:
        tool = self._get_tool()
        result = await tool.execute(
            "call_1", {"pattern": "nonexistent_pattern_xyz", "path": "."}
        )
        assert not result.is_error
        assert "no matches" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_include_filter(self) -> None:
        tool = self._get_tool()
        result = await tool.execute(
            "call_1",
            {"pattern": "hello", "path": ".", "include": "*.py"},
        )
        assert not result.is_error
        # Should find hello in main.py but not in README.md
        text = result.content[0].text
        assert "main.py" in text or "hello" in text

    @pytest.mark.asyncio
    async def test_missing_pattern(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"pattern": ""})
        assert result.is_error

    @pytest.mark.asyncio
    async def test_nonexistent_path(self) -> None:
        tool = self._get_tool()
        result = await tool.execute(
            "call_1", {"pattern": "test", "path": "/nonexistent"}
        )
        assert result.is_error
