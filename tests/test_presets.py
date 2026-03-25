"""Tests for isotope-agents presets."""

from __future__ import annotations

import pytest

from isotope_agents.presets import (
    ASSISTANT_PRESET,
    CODING_PRESET,
    MINIMAL_PRESET,
    PRESETS,
    Preset,
)
from isotope_agents.tools import TOOL_FACTORIES


class TestPresets:
    """Test preset definitions and validity."""

    def test_all_presets_registered(self) -> None:
        """All expected presets are in the registry."""
        assert set(PRESETS.keys()) == {"coding", "assistant", "minimal"}

    def test_coding_preset_has_all_tools(self) -> None:
        """Coding preset includes all coding tools."""
        expected_tools = {"bash", "read", "write", "edit", "grep", "glob"}
        assert set(CODING_PRESET.tools) == expected_tools

    def test_assistant_preset_has_basic_tools(self) -> None:
        """Assistant preset includes basic tools."""
        expected_tools = {"bash", "read", "write"}
        assert set(ASSISTANT_PRESET.tools) == expected_tools

    def test_minimal_preset_has_no_tools(self) -> None:
        """Minimal preset has no tools."""
        assert MINIMAL_PRESET.tools == []

    def test_minimal_preset_has_empty_system_prompt(self) -> None:
        """Minimal preset has no system prompt."""
        assert MINIMAL_PRESET.system_prompt == ""

    @pytest.mark.parametrize("name", list(PRESETS.keys()))
    def test_preset_has_name(self, name: str) -> None:
        """Each preset has a matching name attribute."""
        preset = PRESETS[name]
        assert preset.name == name

    @pytest.mark.parametrize("name", list(PRESETS.keys()))
    def test_preset_has_description(self, name: str) -> None:
        """Each preset has a description (can be empty for minimal)."""
        preset = PRESETS[name]
        assert isinstance(preset.description, str)

    @pytest.mark.parametrize("name", list(PRESETS.keys()))
    def test_preset_tools_are_valid(self, name: str) -> None:
        """All tool names in presets are registered in the tool registry."""
        preset = PRESETS[name]
        for tool_name in preset.tools:
            assert tool_name in TOOL_FACTORIES, (
                f"Preset '{name}' references unknown tool '{tool_name}'"
            )

    @pytest.mark.parametrize("name", ["coding", "assistant"])
    def test_non_minimal_presets_have_system_prompt(self, name: str) -> None:
        """Coding and assistant presets have non-empty system prompts."""
        preset = PRESETS[name]
        assert len(preset.system_prompt) > 50

    def test_custom_preset(self) -> None:
        """Custom presets can be created."""
        custom = Preset(
            name="custom",
            system_prompt="Custom prompt",
            tools=["bash"],
            description="A custom preset",
        )
        assert custom.name == "custom"
        assert custom.tools == ["bash"]
