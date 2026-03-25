"""Tests for IsotopeAgent wrapper."""

from __future__ import annotations

import os
import tempfile

import pytest

from isotope_agents.agent import IsotopeAgent
from isotope_agents.config import IsotopeConfig, ProviderConfig
from isotope_agents.presets import CODING_PRESET


class TestIsotopeAgent:
    """Test IsotopeAgent construction and configuration."""

    def test_create_with_preset_name(self) -> None:
        """Agent can be created with a preset name string."""
        agent = IsotopeAgent(preset="coding")
        assert agent.preset.name == "coding"
        assert len(agent.tools) == 6  # bash, read, write, edit, grep, glob

    def test_create_with_preset_object(self) -> None:
        """Agent can be created with a Preset object."""
        agent = IsotopeAgent(preset=CODING_PRESET)
        assert agent.preset.name == "coding"

    def test_create_with_minimal_preset(self) -> None:
        """Minimal preset creates agent with no tools."""
        agent = IsotopeAgent(preset="minimal")
        assert agent.preset.name == "minimal"
        assert len(agent.tools) == 0

    def test_unknown_preset_raises(self) -> None:
        """Unknown preset name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown preset"):
            IsotopeAgent(preset="nonexistent")

    def test_model_override(self) -> None:
        """Model can be overridden via constructor."""
        agent = IsotopeAgent(preset="minimal", model="gpt-4o")
        assert agent.model == "gpt-4o"

    def test_system_prompt_override(self) -> None:
        """System prompt can be overridden."""
        agent = IsotopeAgent(preset="coding", system_prompt="Custom prompt")
        assert agent.agent.state.system_prompt == "Custom prompt"

    def test_set_model(self) -> None:
        """set_model changes the active model."""
        agent = IsotopeAgent(preset="minimal")
        agent.set_model("claude-sonnet-4-20250514")
        assert agent.model == "claude-sonnet-4-20250514"

    def test_set_system_prompt(self) -> None:
        """set_system_prompt updates the underlying agent."""
        agent = IsotopeAgent(preset="minimal")
        agent.set_system_prompt("New prompt")
        assert agent.agent.state.system_prompt == "New prompt"

    def test_set_tools_enabled(self) -> None:
        """Tools can be toggled on and off."""
        agent = IsotopeAgent(preset="coding")
        assert len(agent.agent.state.tools) == 6

        agent.set_tools_enabled(False)
        assert len(agent.agent.state.tools) == 0

        agent.set_tools_enabled(True)
        assert len(agent.agent.state.tools) == 6

    def test_config_override(self) -> None:
        """Config can be provided directly."""
        config = IsotopeConfig(
            preset="assistant",
            model="test-model",
            provider=ProviderConfig(base_url="http://example.com/v1"),
        )
        agent = IsotopeAgent(preset="assistant", config=config)
        assert agent.model == "test-model"

    def test_extra_tools(self) -> None:
        """Extra tools are appended to preset tools."""
        from isotope_agents.tools.bash import make_bash_tool

        extra = make_bash_tool()
        extra.name = "extra_bash"

        agent = IsotopeAgent(preset="minimal", extra_tools=[extra])
        assert len(agent.tools) == 1
        assert agent.tools[0].name == "extra_bash"


class TestIsotopeConfig:
    """Test config loading."""

    def test_default_config(self) -> None:
        """Default config has sensible values."""
        config = IsotopeConfig()
        assert config.preset == "coding"
        assert config.model == "claude-opus-4.6"
        assert config.provider.base_url == "http://localhost:4141/v1"

    def test_load_missing_file(self) -> None:
        """Loading a missing config file returns defaults."""
        config = IsotopeConfig.load("/nonexistent/config.yaml")
        assert config.preset == "coding"
        assert config.model == "claude-opus-4.6"

    def test_load_valid_yaml(self) -> None:
        """Loading a valid YAML config works."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                "preset: assistant\n"
                "model: gpt-4o\n"
                "provider:\n"
                "  base_url: http://example.com/v1\n"
                "  api_key: test-key\n"
            )
            path = f.name

        try:
            config = IsotopeConfig.load(path)
            assert config.preset == "assistant"
            assert config.model == "gpt-4o"
            assert config.provider.base_url == "http://example.com/v1"
            assert config.provider.api_key == "test-key"
        finally:
            os.unlink(path)

    def test_load_empty_yaml(self) -> None:
        """Loading an empty YAML file returns defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            path = f.name

        try:
            config = IsotopeConfig.load(path)
            assert config.preset == "coding"
        finally:
            os.unlink(path)
