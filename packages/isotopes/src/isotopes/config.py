"""Configuration management for isotopes.

Loads settings from ~/.isotopes/settings.json with env var expansion.
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
    """Main configuration for isotopes."""

    model: str = "default"
    preset: str = "coding"
    system_prompt: str = "none"  # "none" | "default" | "custom"
    debug: bool = False
    sessions_dir: str = "~/.isotopes/sessions"
    skills: list[str] = field(default_factory=lambda: ["~/.isotopes/skills/"])
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

    skills_raw = raw.get("skills", ["~/.isotopes/skills/"])
    if not isinstance(skills_raw, list):
        skills_raw = ["~/.isotopes/skills/"]
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

    # system_prompt mode: "none" | "default" | "custom"
    sp_raw = raw.get("system_prompt", "none")
    system_prompt = str(sp_raw) if sp_raw is not None else "none"
    if system_prompt not in ("none", "default", "custom"):
        system_prompt = "none"

    return IsotopeConfig(
        model=str(raw.get("model", "default")),
        preset=str(raw.get("preset", "coding")),
        system_prompt=system_prompt,
        debug=bool(raw.get("debug", False)),
        sessions_dir=str(raw.get("sessions_dir", "~/.isotopes/sessions")),
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
# Dynamic model listing
# ---------------------------------------------------------------------------

# Fallback model lists when API fetch fails
_FALLBACK_MODELS: dict[str, list[str]] = {
    "anthropic": [
        "claude-sonnet-4.6-20260301",
        "claude-opus-4.6-20260301",
        "claude-haiku-4.5-20241022",
    ],
    "openai": [
        "gpt-5.4",
        "gpt-5.2",
        "o3",
    ],
    "minimax": ["MiniMax-M2.7"],
    "minimax-global": ["MiniMax-M2.7"],
    "proxy": [],
}


async def fetch_available_models(
    base_url: str,
    api_key: str = "",
    provider_type: str = "proxy",
    *,
    timeout: float = 8.0,
    max_models: int = 20,
) -> list[str]:
    """Fetch available models from a provider's API.

    For OpenAI-compatible APIs: GET {base_url}/models
    For Anthropic: GET https://api.anthropic.com/v1/models

    Returns a deduplicated, filtered, ranked list of model IDs (capped at
    *max_models*), or the fallback list on failure.
    """
    import asyncio
    import urllib.error
    import urllib.request

    fallback = _FALLBACK_MODELS.get(provider_type, [])

    def _do_fetch() -> list[str]:
        url = base_url.rstrip("/") + "/models"
        headers: dict[str, str] = {}

        if provider_type == "anthropic":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        elif api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())

        if not isinstance(data, dict) or "data" not in data:
            return fallback or []

        raw_ids: list[str] = []
        for m in data["data"]:
            model_id = m.get("id", "")
            if not model_id:
                continue
            raw_ids.append(model_id)

        if not raw_ids:
            return fallback or []

        return _filter_and_rank(raw_ids, max_models)

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_fetch)
    except Exception:
        return fallback or []


# Prefixes that indicate non-chat models (embeddings, moderation, tts, etc.)
_NON_CHAT_PREFIXES = (
    "text-embedding",
    "embedding",
    "text-moderation",
    "moderation",
    "tts-",
    "whisper",
    "dall-e",
    "davinci",
    "babbage",
    "curie",
    "ada",
)

# Date suffix pattern: -YYYYMMDD or -YYYY-MM-DD at end of model ID
_DATE_SUFFIX_RE = re.compile(r"-\d{4}-?\d{2}-?\d{2}$")


def _filter_and_rank(raw_ids: list[str], max_models: int) -> list[str]:
    """Deduplicate, filter non-chat models, and rank for display.

    Ranking prefers models *without* date suffixes (canonical names)
    and sorts alphabetically within each tier.
    """
    # Deduplicate preserving first occurrence order
    seen: set[str] = set()
    unique: list[str] = []
    for mid in raw_ids:
        if mid not in seen:
            seen.add(mid)
            unique.append(mid)

    # Filter out non-chat models
    chat_models: list[str] = []
    for mid in unique:
        lower = mid.lower()
        if any(lower.startswith(p) for p in _NON_CHAT_PREFIXES):
            continue
        chat_models.append(mid)

    if not chat_models:
        return unique[:max_models]  # nothing left after filter — return unfiltered

    # Rank: canonical (no date suffix) first, then dated, both sorted
    canonical: list[str] = []
    dated: list[str] = []
    for mid in chat_models:
        if _DATE_SUFFIX_RE.search(mid):
            dated.append(mid)
        else:
            canonical.append(mid)

    canonical.sort()
    dated.sort()
    ranked = canonical + dated

    total = len(ranked)
    result = ranked[:max_models]
    if total > max_models:
        result.append(f"({total - max_models} more — type a model name directly)")

    return result


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
        from isotopes_core.providers.anthropic import AnthropicProvider

        return AnthropicProvider(
            model=model,
            api_key=api_key or None,
            base_url=base_url or None,
        )
    elif ptype in ("openai", "minimax", "minimax-global"):
        from isotopes_core.providers.openai import OpenAIProvider

        return OpenAIProvider(
            model=model,
            api_key=api_key or None,
            base_url=base_url or None,
        )
    else:  # proxy
        from isotopes_core.providers.proxy import ProxyProvider

        return ProxyProvider(
            model=model,
            api_key=api_key or "not-needed",
            base_url=base_url or "http://localhost:4141/v1",
        )


# ---------------------------------------------------------------------------
# Public loader
# ---------------------------------------------------------------------------

_DEFAULT_JSON_PATH = Path.home() / ".isotopes" / "settings.json"
_DEFAULT_YAML_PATH = Path.home() / ".isotopes" / "config.yaml"


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

                    skills_raw = raw.get("skills", ["~/.isotopes/skills/"])
                    if not isinstance(skills_raw, list):
                        skills_raw = ["~/.isotopes/skills/"]
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
                            raw.get("sessions_dir", "~/.isotopes/sessions")
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
        path: Path to write to. Defaults to ~/.isotopes/settings.json.
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

    # system_prompt mode is always saved
    data["system_prompt"] = config.system_prompt

    if config.skills != ["~/.isotopes/skills/"]:
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


_DEFAULT_AGENT_MD_PATH = Path.home() / ".isotopes" / "agent.md"


def load_agent_md(path: Path | None = None) -> str:
    """Load custom system prompt from agent.md.

    Returns the file contents, or empty string if not found.
    """
    if path is None:
        path = _DEFAULT_AGENT_MD_PATH
    try:
        return path.read_text().strip()
    except (OSError, FileNotFoundError):
        return ""


def save_agent_md(content: str, path: Path | None = None) -> None:
    """Save custom system prompt to agent.md."""
    if path is None:
        path = _DEFAULT_AGENT_MD_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n")
