"""Tests for config module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isotopes.config import (
    IsotopeConfig,
    ProviderConfig,
    _filter_and_rank,
    create_provider,
    detect_provider_from_env,
    fetch_available_models,
    load_agent_md,
    load_config,
    save_agent_md,
    save_config,
)


class TestLoadConfig:
    """Tests for load_config."""

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        """Missing config file returns default config."""
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.model == "default"
        assert config.preset == "coding"
        assert config.debug is False
        assert config.provider.base_url == "http://localhost:4141/v1"
        assert config.provider.type == "proxy"

    def test_load_full_yaml_config(self, tmp_path: Path) -> None:
        """Load a complete YAML config file (legacy format)."""
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

    def test_load_json_config(self, tmp_path: Path) -> None:
        """Load a JSON settings file."""
        cfg_file = tmp_path / "settings.json"
        cfg_file.write_text(
            json.dumps(
                {
                    "model": "claude-opus-4",
                    "preset": "coding",
                    "provider": {
                        "type": "anthropic",
                        "base_url": "https://api.anthropic.com",
                        "api_key": "sk-ant-test",
                    },
                }
            )
        )
        config = load_config(cfg_file)
        assert config.model == "claude-opus-4"
        assert config.provider.type == "anthropic"
        assert config.provider.base_url == "https://api.anthropic.com"
        assert config.provider.api_key == "sk-ant-test"

    def test_json_provider_type_sets_default_base_url(self, tmp_path: Path) -> None:
        """Provider type auto-resolves base_url when not specified."""
        cfg_file = tmp_path / "settings.json"
        cfg_file.write_text(
            json.dumps({"provider": {"type": "openai", "api_key": "sk-test"}})
        )
        config = load_config(cfg_file)
        assert config.provider.type == "openai"
        assert config.provider.base_url == "https://api.openai.com/v1"

    def test_partial_config(self, tmp_path: Path) -> None:
        """Partial config uses defaults for missing fields."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("model: claude-sonnet\n")
        config = load_config(cfg_file)
        assert config.model == "claude-sonnet"
        assert config.preset == "coding"
        assert config.debug is False

    def test_env_var_expansion(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Environment variables in ${VAR} format are expanded."""
        monkeypatch.setenv("TEST_API_KEY", "sk-from-env")
        monkeypatch.setenv("TEST_URL", "http://env-host:9090")
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "provider:\n  base_url: ${TEST_URL}\n  api_key: ${TEST_API_KEY}\n"
        )
        config = load_config(cfg_file)
        assert config.provider.api_key == "sk-from-env"
        assert config.provider.base_url == "http://env-host:9090"

    def test_env_var_not_set_keeps_placeholder(self, tmp_path: Path) -> None:
        """Unset env vars keep the ${VAR} placeholder."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("provider:\n  api_key: ${NONEXISTENT_VAR_12345}\n")
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
        cfg_file.write_text("tools:\n  - mypackage.tools.custom\n  - another.module\n")
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


class TestDetectProviderFromEnv:
    """Tests for env var auto-detection."""

    def test_anthropic_key_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ANTHROPIC_API_KEY is detected first."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        config = detect_provider_from_env()
        assert config is not None
        assert config.provider.type == "anthropic"
        assert config.provider.api_key == "sk-ant-test"
        assert config.from_env is True

    def test_openai_key_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OPENAI_API_KEY detected when no Anthropic key."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        config = detect_provider_from_env()
        assert config is not None
        assert config.provider.type == "openai"

    def test_minimax_key_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """MINIMAX_API_KEY detected when no others."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("MINIMAX_API_KEY", "mm-test")
        config = detect_provider_from_env()
        assert config is not None
        assert config.provider.type == "minimax"

    def test_anthropic_wins_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Anthropic takes priority over OpenAI."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-oai")
        config = detect_provider_from_env()
        assert config is not None
        assert config.provider.type == "anthropic"

    def test_no_keys_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No env vars returns None."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        assert detect_provider_from_env() is None


class TestCreateProvider:
    """Tests for provider factory."""

    def test_anthropic_provider(self) -> None:
        """Anthropic type creates AnthropicProvider."""
        from isotopes_core.providers.anthropic import AnthropicProvider

        config = IsotopeConfig(
            provider=ProviderConfig(
                type="anthropic",
                base_url="https://api.anthropic.com",
                api_key="sk-ant-test",
            )
        )
        provider = create_provider("claude-sonnet-4", config)
        assert isinstance(provider, AnthropicProvider)

    def test_openai_provider(self) -> None:
        """OpenAI type creates OpenAIProvider."""
        from isotopes_core.providers.openai import OpenAIProvider

        config = IsotopeConfig(
            provider=ProviderConfig(
                type="openai",
                base_url="https://api.openai.com/v1",
                api_key="sk-test",
            )
        )
        provider = create_provider("gpt-4.1", config)
        assert isinstance(provider, OpenAIProvider)

    def test_minimax_provider(self) -> None:
        """MiniMax type creates OpenAIProvider (compat)."""
        from isotopes_core.providers.openai import OpenAIProvider

        config = IsotopeConfig(
            provider=ProviderConfig(
                type="minimax",
                base_url="https://api.minimaxi.com/v1",
                api_key="mm-test",
            )
        )
        provider = create_provider("MiniMax-M1", config)
        assert isinstance(provider, OpenAIProvider)

    def test_proxy_provider(self) -> None:
        """Proxy type creates ProxyProvider."""
        from isotopes_core.providers.proxy import ProxyProvider

        config = IsotopeConfig(
            provider=ProviderConfig(
                type="proxy",
                base_url="http://localhost:4141/v1",
            )
        )
        provider = create_provider("claude-sonnet-4", config)
        assert isinstance(provider, ProxyProvider)

    def test_unknown_type_defaults_to_proxy(self) -> None:
        """Unknown provider type falls back to proxy."""
        from isotopes_core.providers.proxy import ProxyProvider

        config = IsotopeConfig(
            provider=ProviderConfig(type="unknown", base_url="http://custom:8080")
        )
        provider = create_provider("test-model", config)
        assert isinstance(provider, ProxyProvider)


class TestSaveConfig:
    """Tests for save_config."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """Config survives save/load roundtrip."""
        cfg_path = tmp_path / "settings.json"
        config = IsotopeConfig(
            model="claude-opus-4",
            preset="coding",
            provider=ProviderConfig(
                type="anthropic",
                base_url="https://api.anthropic.com",
                api_key="sk-ant-test",
            ),
        )
        save_config(config, cfg_path)
        loaded = load_config(cfg_path)
        assert loaded.model == "claude-opus-4"
        assert loaded.provider.type == "anthropic"
        assert loaded.provider.api_key == "sk-ant-test"

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        """save_config creates parent directories."""
        cfg_path = tmp_path / "deep" / "nested" / "settings.json"
        save_config(IsotopeConfig(), cfg_path)
        assert cfg_path.exists()

    def test_system_prompt_mode_roundtrip(self, tmp_path: Path) -> None:
        """system_prompt mode survives save/load roundtrip."""
        cfg_path = tmp_path / "settings.json"
        config = IsotopeConfig(system_prompt="custom")
        save_config(config, cfg_path)
        loaded = load_config(cfg_path)
        assert loaded.system_prompt == "custom"

    def test_system_prompt_default_mode(self, tmp_path: Path) -> None:
        """'default' mode persists correctly."""
        cfg_path = tmp_path / "settings.json"
        config = IsotopeConfig(system_prompt="default")
        save_config(config, cfg_path)
        loaded = load_config(cfg_path)
        assert loaded.system_prompt == "default"

    def test_system_prompt_invalid_mode_normalizes(self, tmp_path: Path) -> None:
        """Invalid system_prompt mode normalizes to 'none'."""
        cfg_path = tmp_path / "settings.json"
        cfg_path.write_text(json.dumps({"system_prompt": "invalid_value"}))
        loaded = load_config(cfg_path)
        assert loaded.system_prompt == "none"


class TestAgentMd:
    """Tests for agent.md read/write."""

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        """agent.md content survives roundtrip."""
        md_path = tmp_path / "agent.md"
        save_agent_md("You are a helpful coding assistant.", md_path)
        assert load_agent_md(md_path) == "You are a helpful coding assistant."

    def test_load_missing_returns_empty(self, tmp_path: Path) -> None:
        """Missing agent.md returns empty string."""
        assert load_agent_md(tmp_path / "nonexistent.md") == ""

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        """save_agent_md creates parent directories."""
        md_path = tmp_path / "deep" / "agent.md"
        save_agent_md("test prompt", md_path)
        assert md_path.exists()
        assert load_agent_md(md_path) == "test prompt"


class TestYamlMigration:
    """Tests for YAML → JSON migration."""

    def test_migrate_on_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Loading with no JSON but existing YAML triggers migration."""
        import isotopes.config as config_mod

        yaml_path = tmp_path / "config.yaml"
        json_path = tmp_path / "settings.json"
        yaml_path.write_text(
            "model: gpt-4o\nprovider:\n  base_url: http://localhost:8080\n  api_key: sk-test\n"
        )

        monkeypatch.setattr(config_mod, "_DEFAULT_JSON_PATH", json_path)
        monkeypatch.setattr(config_mod, "_DEFAULT_YAML_PATH", yaml_path)
        # Clear env vars to prevent auto-detection
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

        config = load_config()
        assert config.model == "gpt-4o"
        assert json_path.exists()
        # Verify JSON was written correctly
        with open(json_path) as f:
            data = json.load(f)
        assert data["provider"]["type"] == "proxy"


class TestFilterAndRank:
    """Tests for _filter_and_rank model list processing."""

    def test_filters_embedding_models(self) -> None:
        """Embedding models are removed."""
        raw = ["gpt-5.4", "text-embedding-3-large", "text-embedding-ada-002", "o3"]
        result = _filter_and_rank(raw, max_models=20)
        assert "gpt-5.4" in result
        assert "o3" in result
        assert all("embedding" not in m for m in result)

    def test_filters_non_chat_models(self) -> None:
        """TTS, whisper, dall-e, moderation models are removed."""
        raw = ["gpt-5.4", "tts-1", "whisper-1", "dall-e-3", "text-moderation-latest"]
        result = _filter_and_rank(raw, max_models=20)
        assert result == ["gpt-5.4"]

    def test_deduplicates(self) -> None:
        """Duplicate model IDs are removed."""
        raw = ["gpt-4", "gpt-4", "gpt-5.4", "gpt-5.4"]
        result = _filter_and_rank(raw, max_models=20)
        assert result == ["gpt-4", "gpt-5.4"]

    def test_canonical_before_dated(self) -> None:
        """Models without date suffixes rank before dated ones."""
        raw = [
            "claude-sonnet-4.6-20260301",
            "claude-sonnet-4.6",
            "claude-opus-4.6-20260301",
            "claude-opus-4.6",
        ]
        result = _filter_and_rank(raw, max_models=20)
        assert result.index("claude-opus-4.6") < result.index(
            "claude-opus-4.6-20260301"
        )
        assert result.index("claude-sonnet-4.6") < result.index(
            "claude-sonnet-4.6-20260301"
        )

    def test_caps_at_max_models(self) -> None:
        """List is capped and includes overflow hint."""
        raw = [f"model-{i:02d}" for i in range(30)]
        result = _filter_and_rank(raw, max_models=10)
        # 10 models + 1 hint entry
        assert len(result) == 11
        assert result[-1].startswith("(20 more")

    def test_empty_input(self) -> None:
        """Empty input returns empty list."""
        assert _filter_and_rank([], max_models=20) == []

    def test_all_filtered_returns_unfiltered(self) -> None:
        """If all models are non-chat, returns unfiltered capped list."""
        raw = ["text-embedding-1", "text-embedding-2", "text-embedding-3"]
        result = _filter_and_rank(raw, max_models=20)
        # Falls back to unfiltered since everything was filtered
        assert len(result) == 3


class TestFetchAvailableModels:
    """Tests for fetch_available_models."""

    @pytest.mark.asyncio
    async def test_returns_fallback_on_network_error(self) -> None:
        """Returns fallback models when API is unreachable."""
        models = await fetch_available_models(
            "http://localhost:1",  # unreachable
            provider_type="anthropic",
            timeout=1.0,
        )
        assert "claude-sonnet-4.6-20260301" in models

    @pytest.mark.asyncio
    async def test_returns_fallback_for_unknown_provider(self) -> None:
        """Unknown provider type returns empty list on failure."""
        models = await fetch_available_models(
            "http://localhost:1",
            provider_type="unknown",
            timeout=1.0,
        )
        assert models == []

    @pytest.mark.asyncio
    async def test_parses_filters_and_deduplicates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Parses OpenAI response, filters embeddings, deduplicates."""
        import urllib.request

        fake_response = json.dumps(
            {
                "data": [
                    {"id": "gpt-5.4"},
                    {"id": "gpt-5.2"},
                    {"id": "gpt-5.4"},  # duplicate
                    {"id": "text-embedding-3-large"},  # non-chat
                    {"id": "gpt-4.1"},
                ]
            }
        ).encode()

        class FakeResp:
            def read(self) -> bytes:
                return fake_response

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        models = await fetch_available_models(
            "https://api.openai.com/v1",
            api_key="sk-test",
            provider_type="openai",
        )
        assert "gpt-5.4" in models
        assert "gpt-5.2" in models
        assert "gpt-4.1" in models
        assert "text-embedding-3-large" not in models
        assert models.count("gpt-5.4") == 1

    @pytest.mark.asyncio
    async def test_empty_data_returns_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Empty data list returns fallback."""
        import urllib.request

        fake_response = json.dumps({"data": []}).encode()

        class FakeResp:
            def read(self) -> bytes:
                return fake_response

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeResp())

        models = await fetch_available_models(
            "https://api.openai.com/v1",
            provider_type="openai",
        )
        # Falls back to hardcoded list
        assert "gpt-5.4" in models
