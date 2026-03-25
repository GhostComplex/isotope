"""Tests for preset system."""

from __future__ import annotations

import os

import pytest

from isotope_agents.presets import (
    ASSISTANT,
    CODING,
    MINIMAL,
    PRESETS,
    Preset,
    get_preset,
)


class TestPresets:
    """Tests for the preset system."""

    def test_coding_preset_has_all_tools(self) -> None:
        """Coding preset has read, write, edit, bash, grep, glob."""
        tool_names = {t.name for t in CODING.tools}
        assert tool_names == {
            "read_file", "write_file", "edit_file", "bash", "grep", "glob_tool"
        }

    def test_assistant_preset_no_write(self) -> None:
        """Assistant preset has no write or edit tools."""
        tool_names = {t.name for t in ASSISTANT.tools}
        assert "write_file" not in tool_names
        assert "edit_file" not in tool_names
        assert "read_file" in tool_names
        assert "bash" in tool_names

    def test_minimal_preset_bash_only(self) -> None:
        """Minimal preset has only bash."""
        tool_names = {t.name for t in MINIMAL.tools}
        assert tool_names == {"bash"}

    def test_get_preset_valid(self) -> None:
        """get_preset returns correct preset."""
        assert get_preset("coding") is CODING
        assert get_preset("assistant") is ASSISTANT
        assert get_preset("minimal") is MINIMAL

    def test_get_preset_invalid(self) -> None:
        """get_preset raises KeyError for unknown presets."""
        with pytest.raises(KeyError, match="Unknown preset"):
            get_preset("nonexistent")

    def test_format_system_prompt(self) -> None:
        """System prompt accepts cwd placeholder."""
        formatted = CODING.format_system_prompt(cwd="/test/path")
        assert "/test/path" in formatted

    def test_all_presets_registered(self) -> None:
        """All presets are in the registry."""
        assert set(PRESETS.keys()) == {"coding", "assistant", "minimal"}

    def test_custom_preset(self) -> None:
        """Custom presets can be created."""
        custom = Preset(
            name="custom",
            system_prompt="You are {cwd}.",
            tools=[],
            description="A custom preset.",
        )
        assert custom.format_system_prompt(cwd="/home") == "You are /home."
