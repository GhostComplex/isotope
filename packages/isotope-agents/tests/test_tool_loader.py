"""Tests for tool_loader module."""

from __future__ import annotations

import pytest

from isotope_core.tools import Tool

from isotope_agents.tool_loader import load_tools_from_config


class TestLoadToolsFromConfig:
    """Tests for load_tools_from_config."""

    def test_load_real_module(self) -> None:
        """Loading isotope_agents.tools.bash yields at least one Tool."""
        tools = load_tools_from_config(["isotope_agents.tools.bash"])
        assert len(tools) >= 1
        assert all(isinstance(t, Tool) for t in tools)
        names = [t.name for t in tools]
        assert "bash" in names

    def test_nonexistent_module_raises(self) -> None:
        """A nonexistent module path raises ImportError."""
        with pytest.raises(ImportError):
            load_tools_from_config(["nonexistent.module.path.xyz"])

    def test_module_with_no_tools(self) -> None:
        """A module with no Tool instances returns an empty list."""
        # isotope_agents.tools only exports truncate_output, no Tool instances
        tools = load_tools_from_config(["isotope_agents.tools"])
        assert tools == []

    def test_multiple_modules(self) -> None:
        """Loading multiple modules collects tools from all of them."""
        tools = load_tools_from_config(
            [
                "isotope_agents.tools.bash",
                "isotope_agents.tools.read",
            ]
        )
        assert len(tools) >= 2
        names = [t.name for t in tools]
        assert "bash" in names
        assert "read_file" in names

    def test_empty_list(self) -> None:
        """An empty tool_paths list returns an empty list."""
        tools = load_tools_from_config([])
        assert tools == []
