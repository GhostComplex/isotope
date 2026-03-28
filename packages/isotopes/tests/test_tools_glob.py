"""Tests for glob tool."""

from __future__ import annotations

import os
import tempfile

import pytest

from isotopes_core.tools import Tool


class TestGlobTool:
    """Tests for the glob_tool."""

    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        # Create test structure
        os.makedirs(os.path.join(self.tmpdir, "src", "utils"), exist_ok=True)
        for name in ["main.py", "app.py"]:
            with open(os.path.join(self.tmpdir, "src", name), "w") as f:
                f.write("")
        with open(os.path.join(self.tmpdir, "src", "utils", "helpers.py"), "w") as f:
            f.write("")
        with open(os.path.join(self.tmpdir, "README.md"), "w") as f:
            f.write("")
        with open(os.path.join(self.tmpdir, "config.yaml"), "w") as f:
            f.write("")

    @pytest.fixture(autouse=True)
    def _patch_workspace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import isotopes.tools.glob as glob_mod

        monkeypatch.setattr(glob_mod, "_WORKSPACE", self.tmpdir)

    def _get_tool(self) -> Tool:
        from isotopes.tools.glob import glob_tool

        return glob_tool

    @pytest.mark.asyncio
    async def test_recursive_python_files(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"pattern": "**/*.py"})
        assert not result.is_error
        text = result.content[0].text
        assert "main.py" in text
        assert "helpers.py" in text

    @pytest.mark.asyncio
    async def test_single_level_glob(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"pattern": "*.md"})
        assert not result.is_error
        assert "README.md" in result.content[0].text

    @pytest.mark.asyncio
    async def test_no_matches(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"pattern": "*.rs"})
        assert not result.is_error
        assert "no files" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_missing_pattern(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"pattern": ""})
        assert result.is_error

    @pytest.mark.asyncio
    async def test_nonexistent_path(self) -> None:
        tool = self._get_tool()
        result = await tool.execute(
            "call_1", {"pattern": "*.py", "path": "/nonexistent"}
        )
        assert result.is_error

    @pytest.mark.asyncio
    async def test_results_sorted(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"pattern": "**/*.py"})
        lines = result.content[0].text.strip().splitlines()
        assert lines == sorted(lines)
