"""Tests for the bash tool."""

from __future__ import annotations

import tempfile

import pytest

from isotopes_core.tools import Tool


class TestBashTool:
    """Tests for the bash tool."""

    def setup_method(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    @pytest.fixture(autouse=True)
    def _patch_workspace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import isotopes.tools.bash as bash_mod

        monkeypatch.setattr(bash_mod, "_WORKSPACE", self.tmpdir)

    def _get_tool(self) -> Tool:
        from isotopes.tools.bash import bash

        return bash

    @pytest.mark.asyncio
    async def test_simple_command(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"command": "echo hello"})
        assert not result.is_error
        assert "hello" in result.content[0].text

    @pytest.mark.asyncio
    async def test_exit_code_zero(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"command": "true"})
        assert not result.is_error
        assert "Exit code: 0" in result.content[0].text

    @pytest.mark.asyncio
    async def test_nonzero_exit_code(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"command": "false"})
        assert result.is_error
        assert "Exit code: 1" in result.content[0].text

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"command": "sleep 10", "timeout": 1})
        assert result.is_error
        assert "timed out" in result.content[0].text.lower()

    @pytest.mark.asyncio
    async def test_timeout_capped(self) -> None:
        """Timeout is capped at MAX_TIMEOUT."""
        tool = self._get_tool()
        # Should not actually wait 999 seconds
        result = await tool.execute("call_1", {"command": "echo fast", "timeout": 999})
        assert not result.is_error
        assert "fast" in result.content[0].text

    @pytest.mark.asyncio
    async def test_empty_command(self) -> None:
        tool = self._get_tool()
        result = await tool.execute("call_1", {"command": ""})
        assert result.is_error
