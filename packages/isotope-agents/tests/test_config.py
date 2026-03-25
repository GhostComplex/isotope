"""Tests for config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from isotope_agents.config import IsotopeConfig, load_config


class TestLoadConfig:
    """Tests for load_config."""

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """Missing config file returns default config."""
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.model == "default"
        assert config.preset == "coding"
        assert config.debug is False
        assert config.provider.base_url == "http://localhost:4141"

    def test_load_full_config(self, tmp_path: Path) -> None:
        """Load a complete config file."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "model: gpt-4o\n"
            "preset: assistant\n"
            "debug: true\n"
            "sessions_dir: /tmp/sessions\n"
            "provider:\n"
            "  base_url: http://localhost:8080\n"
            "  api_key: sk-test-123\n"
        )
        config = load_config(cfg_file)
        assert config.model == "gpt-4o"
        assert config.preset == "assistant"
        assert config.debug is True
        assert config.sessions_dir == "/tmp/sessions"
        assert config.provider.base_url == "http://localhost:8080"
        assert config.provider.api_key == "sk-test-123"

    def test_partial_config(self, tmp_path: Path) -> None:
        """Partial config uses defaults for missing fields."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("model: claude-sonnet\n")
        config = load_config(cfg_file)
        assert config.model == "claude-sonnet"
        assert config.preset == "coding"  # default
        assert config.debug is False  # default
        assert config.provider.base_url == "http://localhost:4141"  # default

    def test_env_var_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment variables in ${VAR} format are expanded."""
        monkeypatch.setenv("TEST_API_KEY", "sk-from-env")
        monkeypatch.setenv("TEST_URL", "http://env-host:9090")
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "provider:\n"
            "  base_url: ${TEST_URL}\n"
            "  api_key: ${TEST_API_KEY}\n"
        )
        config = load_config(cfg_file)
        assert config.provider.api_key == "sk-from-env"
        assert config.provider.base_url == "http://env-host:9090"

    def test_env_var_not_set_keeps_placeholder(
        self, tmp_path: Path
    ) -> None:
        """Unset env vars keep the ${VAR} placeholder."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "provider:\n"
            "  api_key: ${NONEXISTENT_VAR_12345}\n"
        )
        config = load_config(cfg_file)
        assert config.provider.api_key == "${NONEXISTENT_VAR_12345}"

    def test_empty_file_returns_defaults(self, tmp_path: Path) -> None:
        """Empty config file returns defaults."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("")
        config = load_config(cfg_file)
        assert config.model == "default"

    def test_invalid_yaml_returns_defaults(self, tmp_path: Path) -> None:
        """Non-dict YAML returns defaults."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("just a string\n")
        config = load_config(cfg_file)
        assert config.model == "default"

    def test_tools_default_empty(self) -> None:
        """Default config has an empty tools list."""
        config = IsotopeConfig()
        assert config.tools == []

    def test_tools_in_config(self, tmp_path: Path) -> None:
        """Tools list is loaded from YAML config."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "tools:\n"
            "  - mypackage.tools.custom\n"
            "  - another.module\n"
        )
        config = load_config(cfg_file)
        assert config.tools == ["mypackage.tools.custom", "another.module"]

    def test_tools_invalid_type_returns_empty(self, tmp_path: Path) -> None:
        """Non-list tools value falls back to empty list."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("tools: not-a-list\n")
        config = load_config(cfg_file)
        assert config.tools == []

    def test_tools_missing_returns_empty(self, tmp_path: Path) -> None:
        """Missing tools key results in empty list."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("model: default\n")
        config = load_config(cfg_file)
        assert config.tools == []
