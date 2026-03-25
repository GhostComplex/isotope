"""Tests for IsotopeAgent."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from isotope_agents.agent import IsotopeAgent
from isotope_agents.presets import ASSISTANT, CODING, MINIMAL


class TestIsotopeAgent:
    """Tests for IsotopeAgent initialization and configuration."""

    def _mock_provider(self) -> MagicMock:
        """Create a mock provider."""
        provider = MagicMock()
        provider.stream = AsyncMock()
        return provider

    def test_default_preset_is_coding(self) -> None:
        """Default preset should be coding."""
        agent = IsotopeAgent(provider=self._mock_provider())
        assert agent.preset.name == "coding"
        tool_names = {t.name for t in agent.tools}
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "bash" in tool_names
        assert "grep" in tool_names

    def test_assistant_preset(self) -> None:
        """Assistant preset excludes write/edit."""
        agent = IsotopeAgent(
            provider=self._mock_provider(), preset="assistant"
        )
        assert agent.preset.name == "assistant"
        tool_names = {t.name for t in agent.tools}
        assert "write_file" not in tool_names
        assert "edit_file" not in tool_names

    def test_minimal_preset(self) -> None:
        """Minimal preset has bash only."""
        agent = IsotopeAgent(
            provider=self._mock_provider(), preset="minimal"
        )
        tool_names = {t.name for t in agent.tools}
        assert tool_names == {"bash"}

    def test_preset_instance(self) -> None:
        """Accept Preset instance directly."""
        agent = IsotopeAgent(
            provider=self._mock_provider(), preset=ASSISTANT
        )
        assert agent.preset is ASSISTANT

    def test_custom_system_prompt(self) -> None:
        """Custom system prompt overrides preset."""
        agent = IsotopeAgent(
            provider=self._mock_provider(),
            system_prompt="Custom prompt",
        )
        assert agent.core._state.system_prompt == "Custom prompt"

    def test_extra_tools(self) -> None:
        """Extra tools are added to preset tools."""
        from isotope_core.tools import auto_tool

        @auto_tool
        async def custom_tool(x: str) -> str:
            """A custom tool.

            Args:
                x: Input.
            """
            return x

        agent = IsotopeAgent(
            provider=self._mock_provider(),
            preset="minimal",
            extra_tools=[custom_tool],
        )
        tool_names = {t.name for t in agent.tools}
        assert "custom_tool" in tool_names
        assert "bash" in tool_names

    def test_workspace_setting(self) -> None:
        """Workspace is set on the agent."""
        agent = IsotopeAgent(
            provider=self._mock_provider(),
            workspace="/test/workspace",
        )
        assert agent.workspace == "/test/workspace"

    def test_invalid_preset_name(self) -> None:
        """Invalid preset name raises KeyError."""
        with pytest.raises(KeyError):
            IsotopeAgent(
                provider=self._mock_provider(), preset="nonexistent"
            )

    def test_core_property(self) -> None:
        """Core property exposes the underlying Agent."""
        from isotope_core import Agent

        agent = IsotopeAgent(provider=self._mock_provider())
        assert isinstance(agent.core, Agent)
