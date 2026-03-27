"""Configuration management for isotope-agents.

Loads settings from ~/.isotope/settings.json with env var expansion.
Supports migration from legacy config.yaml files.
Config priority: CLI flags > env vars > config file > defaults.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Provider type constants
# ---------------------------------------------------------------------------

PROVIDER_TYPES = ("openai", "anthropic", "minimax", "minimax-global", "proxy")

PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-5.4",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4.6-20260301",
    },
    "minimax": {
        "base_url": "https://api.minimaxi.com/v1",
        "env_key": "MINIMAX_API_KEY",
        "default_model": "MiniMax-M2.7",
    },
    "minimax-global": {
        "base_url": "https://api.minimax.io/v1",
        "env_key": "MINIMAX_API_KEY",
        "default_model": "MiniMax-M2.7",
    },
    "proxy": {
        "base_url": "http://localhost:4141/v1",
        "env_key": "",
        "default_model": "claude-sonnet-4.6-20260301",
    },
}


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ProviderConfig:
    """Provider connection settings."""

    type: str = "proxy"
    base_url: str = "http://localhost:4141/v1"
    api_key: str = ""


@dataclass
class McpServerConfig:
    """Configuration for a single MCP server.

    Either ``command`` (stdio transport) or ``url`` (SSE transport) must
    be provided.
    """

    name: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    url: str = ""


@dataclass
class IsotopeConfig:
    """Main configuration for isotope-agents."""

    model: str = "default"
    preset: str = "coding"
    debug: bool = False
    sessions_dir: str = "~/.isotope/sessions"
    skills: list[str] = field(default_factory=lambda: ["~/.isotope/skills/"])
    tools: list[str] = field(default_factory=list)
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    mcp_servers: list[McpServerConfig] = field(default_factory=list)
    from_env: bool = False  # True when config was auto-detected from env vars


# ---------------------------------------------------------------------------
# Env var expansion
# ---------------------------------------------------------------------------

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _expand_env_vars(value: str) -> str:
    """Expand ${VAR} references in a string."""

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    return _ENV_VAR_RE.sub(_replace, value)


def _expand_recursive(data: Any) -> Any:
    """Recursively expand env vars in all string values."""
    if isinstance(data, str):
        return _expand_env_vars(data)
    if isinstance(data, dict):
        return {k: _expand_recursive(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_expand_recursive(v) for v in data]
    return data


# ---------------------------------------------------------------------------
# JSON config loader
# ---------------------------------------------------------------------------


def _parse_config(raw: dict[str, Any]) -> IsotopeConfig:
    """Parse a raw dict (from JSON or migrated YAML) into IsotopeConfig."""
    raw = _expand_recursive(raw)

    provider_data = raw.get("provider", {})
    ptype = str(provider_data.get("type", "proxy"))
    defaults = PROVIDER_DEFAULTS.get(ptype, PROVIDER_DEFAULTS["proxy"])

    provider = ProviderConfig(
        type=ptype,
        base_url=str(provider_data.get("base_url", defaults["base_url"])),
        api_key=str(provider_data.get("api_key", "")),
    )

    skills_raw = raw.get("skills", ["~/.isotope/skills/"])
    if not isinstance(skills_raw, list):
        skills_raw = ["~/.isotope/skills/"]
    skills = [str(s) for s in skills_raw]

    tools_raw = raw.get("tools", [])
    if not isinstance(tools_raw, list):
        tools_raw = []
    tools = [str(t) for t in tools_raw]

    mcp_servers: list[McpServerConfig] = []
    mcp_data = raw.get("mcp", {})
    if isinstance(mcp_data, dict):
        for srv in mcp_data.get("servers", []):
            if isinstance(srv, dict):
                args_raw = srv.get("args", [])
                if not isinstance(args_raw, list):
                    args_raw = []
                mcp_servers.append(
                    McpServerConfig(
                        name=str(srv.get("name", "")),
                        command=str(srv.get("command", "")),
                        args=[str(a) for a in args_raw],
                        url=str(srv.get("url", "")),
                    )
                )

    return IsotopeConfig(
        model=str(raw.get("model", "default")),
        preset=str(raw.get("preset", "coding")),
        debug=bool(raw.get("debug", False)),
        sessions_dir=str(raw.get("sessions_dir", "~/.isotope/sessions")),
        skills=skills,
        tools=tools,
        provider=provider,
        mcp_servers=mcp_servers,
    )


# ---------------------------------------------------------------------------
# YAML → JSON migration
# ---------------------------------------------------------------------------


def _migrate_yaml_to_json(yaml_path: Path, json_path: Path) -> dict[str, Any] | None:
    """Migrate a legacy config.yaml to settings.json.

    Returns the parsed dict on success, or None if migration is not possible.
    """
    try:
        import yaml
    except ImportError:
        return None

    if not yaml_path.exists():
        return None

    try:
        with open(yaml_path) as f:
            raw = yaml.safe_load(f)
    except Exception:
        return None

    if not isinstance(raw, dict):
        return None

    # Add provider.type if missing (legacy configs assumed proxy)
    provider_data = raw.get("provider", {})
    if isinstance(provider_data, dict) and "type" not in provider_data:
        provider_data["type"] = "proxy"
        # Legacy configs used base_url without /v1 suffix for proxy
        base_url = provider_data.get("base_url", "")
        if base_url and not base_url.endswith("/v1"):
            provider_data["base_url"] = base_url + "/v1"
        raw["provider"] = provider_data

    # Write JSON
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(raw, f, indent=2)
        f.write("\n")

    print("Migrated config.yaml → settings.json", file=sys.stderr)
    return raw


# ---------------------------------------------------------------------------
# Env var auto-detection
# ---------------------------------------------------------------------------


def detect_provider_from_env() -> IsotopeConfig | None:
    """Auto-detect provider from environment variables.

    Priority: ANTHROPIC_API_KEY > OPENAI_API_KEY > MINIMAX_API_KEY.
    Returns a config if a key is found, None otherwise.
    """
    detection_order = [
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("minimax", "MINIMAX_API_KEY"),
    ]

    for ptype, env_var in detection_order:
        api_key = os.environ.get(env_var)
        if api_key:
            defaults = PROVIDER_DEFAULTS[ptype]
            provider = ProviderConfig(
                type=ptype,
                base_url=defaults["base_url"],
                api_key=api_key,
            )
            return IsotopeConfig(
                model=defaults["default_model"],
                provider=provider,
                from_env=True,
            )

    return None


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------


def create_provider(model: str, config: IsotopeConfig) -> Any:
    """Create the appropriate provider based on config.

    Args:
        model: Model name to use.
        config: Loaded config with provider settings.

    Returns:
        A provider instance (OpenAIProvider, AnthropicProvider, or ProxyProvider).
    """
    ptype = config.provider.type
    api_key = config.provider.api_key
    base_url = config.provider.base_url

    if ptype == "anthropic":
        from isotope_core.providers.anthropic import AnthropicProvider

        return AnthropicProvider(
            model=model,
            api_key=api_key or None,
            base_url=base_url or None,
        )
    elif ptype in ("openai", "minimax", "minimax-global"):
        from isotope_core.providers.openai import OpenAIProvider

        return OpenAIProvider(
            model=model,
            api_key=api_key or None,
            base_url=base_url or None,
        )
    else:  # proxy
        from isotope_core.providers.proxy import ProxyProvider

        return ProxyProvider(
            model=model,
            api_key=api_key or "not-needed",
            base_url=base_url or "http://localhost:4141/v1",
        )


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

_DEFAULT_JSON_PATH = Path.home() / ".isotope" / "settings.json"
_DEFAULT_YAML_PATH = Path.home() / ".isotope" / "config.yaml"


def load_config(path: Path | None = None) -> IsotopeConfig:
    """Load config from settings.json (or migrate from config.yaml).

    Resolution order:
    1. If settings.json exists → load it
    2. If config.yaml exists → migrate to settings.json, then load
    3. If env vars detected → return env-based config (no file written)
    4. Return defaults (triggers FRE in TUI)

    Args:
        path: Explicit path to a config file (JSON or YAML).

    Returns:
        Loaded configuration with defaults for missing values.
    """
    # Explicit path provided — detect format by extension
    if path is not None:
        if path.suffix in (".json",) and path.exists():
            try:
                with open(path) as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    return _parse_config(raw)
            except (json.JSONDecodeError, OSError):
                pass
            return IsotopeConfig()

        if path.suffix in (".yaml", ".yml") and path.exists():
            # Legacy YAML path — load directly (for backward compat / tests)
            try:
                import yaml

                with open(path) as f:
                    raw = yaml.safe_load(f)
                if isinstance(raw, dict):
                    raw = _expand_recursive(raw)
                    provider_data = raw.get("provider", {})
                    provider = ProviderConfig(
                        type=str(provider_data.get("type", "proxy")),
                        base_url=str(
                            provider_data.get("base_url", "http://localhost:4141")
                        ),
                        api_key=str(provider_data.get("api_key", "")),
                    )

                    skills_raw = raw.get("skills", ["~/.isotope/skills/"])
                    if not isinstance(skills_raw, list):
                        skills_raw = ["~/.isotope/skills/"]
                    skills = [str(s) for s in skills_raw]

                    tools_raw = raw.get("tools", [])
                    if not isinstance(tools_raw, list):
                        tools_raw = []
                    tools = [str(t) for t in tools_raw]

                    mcp_servers: list[McpServerConfig] = []
                    mcp_data = raw.get("mcp", {})
                    if isinstance(mcp_data, dict):
                        for srv in mcp_data.get("servers", []):
                            if isinstance(srv, dict):
                                args_raw = srv.get("args", [])
                                if not isinstance(args_raw, list):
                                    args_raw = []
                                mcp_servers.append(
                                    McpServerConfig(
                                        name=str(srv.get("name", "")),
                                        command=str(srv.get("command", "")),
                                        args=[str(a) for a in args_raw],
                                        url=str(srv.get("url", "")),
                                    )
                                )

                    return IsotopeConfig(
                        model=str(raw.get("model", "default")),
                        preset=str(raw.get("preset", "coding")),
                        debug=bool(raw.get("debug", False)),
                        sessions_dir=str(
                            raw.get("sessions_dir", "~/.isotope/sessions")
                        ),
                        skills=skills,
                        tools=tools,
                        provider=provider,
                        mcp_servers=mcp_servers,
                    )
            except ImportError:
                pass
            except Exception:
                pass
            return IsotopeConfig()

        # Path doesn't exist or unknown extension
        return IsotopeConfig()

    # --- Default resolution order ---

    # 1. settings.json
    if _DEFAULT_JSON_PATH.exists():
        try:
            with open(_DEFAULT_JSON_PATH) as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                return _parse_config(raw)
        except (json.JSONDecodeError, OSError):
            pass

    # 2. Migrate config.yaml → settings.json
    if _DEFAULT_YAML_PATH.exists():
        raw = _migrate_yaml_to_json(_DEFAULT_YAML_PATH, _DEFAULT_JSON_PATH)
        if raw is not None:
            return _parse_config(raw)

    # 3. Env var auto-detection
    env_config = detect_provider_from_env()
    if env_config is not None:
        return env_config

    # 4. Defaults
    return IsotopeConfig()


def save_config(config: IsotopeConfig, path: Path | None = None) -> None:
    """Save config to settings.json.

    Args:
        config: Config to save.
        path: Path to write to. Defaults to ~/.isotope/settings.json.
    """
    if path is None:
        path = _DEFAULT_JSON_PATH

    data: dict[str, Any] = {
        "provider": {
            "type": config.provider.type,
            "base_url": config.provider.base_url,
            "api_key": config.provider.api_key,
        },
        "model": config.model,
        "preset": config.preset,
        "sessions_dir": config.sessions_dir,
    }

    if config.skills != ["~/.isotope/skills/"]:
        data["skills"] = config.skills
    if config.tools:
        data["tools"] = config.tools
    if config.mcp_servers:
        data["mcp"] = {
            "servers": [
                {
                    "name": s.name,
                    "command": s.command,
                    "args": s.args,
                    "url": s.url,
                }
                for s in config.mcp_servers
            ]
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
