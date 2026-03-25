"""Configuration file loading for isotope-agents.

Loads configuration from ~/.isotope/config.yaml with sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderConfig:
    """Provider configuration."""

    base_url: str = "http://localhost:4141/v1"
    api_key: str = "not-needed"


@dataclass
class IsotopeConfig:
    """Top-level isotope-agents configuration.

    Loaded from ~/.isotope/config.yaml or constructed with defaults.
    """

    preset: str = "coding"
    model: str = "claude-opus-4.6"
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    system_prompt: str | None = None
    extra_tools: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path | None = None) -> IsotopeConfig:
        """Load configuration from a YAML file.

        Args:
            path: Path to config file. Defaults to ~/.isotope/config.yaml.

        Returns:
            IsotopeConfig with values from file, falling back to defaults.
        """
        if path is None:
            path = Path(os.path.expanduser("~/.isotope/config.yaml"))
        else:
            path = Path(path)

        if not path.exists():
            return cls()

        try:
            import yaml
        except ImportError:
            return cls()

        try:
            with open(path, encoding="utf-8") as f:
                data: dict[str, Any] = yaml.safe_load(f) or {}
        except Exception:
            return cls()

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> IsotopeConfig:
        """Build config from a parsed YAML dict."""
        provider_data = data.get("provider", {})
        provider = ProviderConfig(
            base_url=provider_data.get("base_url", ProviderConfig.base_url),
            api_key=provider_data.get("api_key", ProviderConfig.api_key),
        )

        return cls(
            preset=data.get("preset", cls.preset),
            model=data.get("model", cls.model),
            provider=provider,
            system_prompt=data.get("system_prompt"),
            extra_tools=data.get("extra_tools", []),
        )
