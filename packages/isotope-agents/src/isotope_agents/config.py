"""Configuration management for isotope-agents.

Loads settings from ~/.isotope/config.yaml with env var expansion.
Config priority: CLI flags > env vars > config file > defaults.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderConfig:
    """Provider connection settings."""

    base_url: str = "http://localhost:4141"
    api_key: str = ""


@dataclass
class IsotopeConfig:
    """Main configuration for isotope-agents."""

    model: str = "default"
    preset: str = "coding"
    debug: bool = False
    sessions_dir: str = "~/.isotope/sessions"
    skills: list[str] = field(default_factory=lambda: ["~/.isotope/skills/"])
    provider: ProviderConfig = field(default_factory=ProviderConfig)


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


def load_config(path: Path | None = None) -> IsotopeConfig:
    """Load config from a YAML file.

    Args:
        path: Path to config file. Defaults to ~/.isotope/config.yaml.

    Returns:
        Loaded configuration with defaults for missing values.
    """
    if path is None:
        path = Path.home() / ".isotope" / "config.yaml"

    if not path.exists():
        return IsotopeConfig()

    try:
        import yaml
    except ImportError:
        return IsotopeConfig()

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        return IsotopeConfig()

    raw = _expand_recursive(raw)

    provider_data = raw.get("provider", {})
    provider = ProviderConfig(
        base_url=str(provider_data.get("base_url", "http://localhost:4141")),
        api_key=str(provider_data.get("api_key", "")),
    )

    skills_raw = raw.get("skills", ["~/.isotope/skills/"])
    if not isinstance(skills_raw, list):
        skills_raw = ["~/.isotope/skills/"]
    skills = [str(s) for s in skills_raw]

    return IsotopeConfig(
        model=str(raw.get("model", "default")),
        preset=str(raw.get("preset", "coding")),
        debug=bool(raw.get("debug", False)),
        sessions_dir=str(raw.get("sessions_dir", "~/.isotope/sessions")),
        skills=skills,
        provider=provider,
    )
