"""IsotopeAgent — high-level agent wrapping isotope-core with presets.

Provides a convenient interface for creating agents with preset-based
tool registration and system prompts.
"""

from __future__ import annotations

from typing import Any

from isotope_core import Agent
from isotope_core.providers.base import Provider
from isotope_core.providers.proxy import ProxyProvider
from isotope_core.tools import Tool

from isotope_agents.config import IsotopeConfig
from isotope_agents.presets import PRESETS, Preset
from isotope_agents.tools import get_tools


class IsotopeAgent:
    """High-level agent that wraps isotope-core Agent with preset support.

    IsotopeAgent resolves tools from a preset, sets the system prompt, and
    delegates to isotope-core's Agent for the actual agent loop.

    Example:
        agent = IsotopeAgent(preset="coding", model="claude-opus-4.6")
        async for event in agent.prompt("Fix the bug in auth.py"):
            print(event)
    """

    def __init__(
        self,
        preset: str | Preset = "coding",
        model: str | None = None,
        provider: Provider | None = None,
        config: IsotopeConfig | None = None,
        extra_tools: list[Tool] | None = None,
        system_prompt: str | None = None,
        **agent_kwargs: Any,
    ) -> None:
        """Initialize an IsotopeAgent.

        Args:
            preset: Preset name or Preset object. Defaults to "coding".
            model: Model name. Overrides config if provided.
            provider: Provider instance. If None, creates ProxyProvider from config.
            config: Configuration object. If None, loads from ~/.isotope/config.yaml.
            extra_tools: Additional tools beyond what the preset defines.
            system_prompt: Override the preset's system prompt.
            **agent_kwargs: Additional kwargs passed to isotope-core Agent.
        """
        # Resolve config
        if config is None:
            config = IsotopeConfig.load()

        # Resolve preset
        if isinstance(preset, str):
            preset_name = preset
            resolved_preset = PRESETS.get(preset_name)
            if resolved_preset is None:
                raise ValueError(
                    f"Unknown preset: {preset_name!r}. "
                    f"Available: {', '.join(PRESETS.keys())}"
                )
        else:
            resolved_preset = preset

        self._preset = resolved_preset
        self._config = config

        # Resolve model
        self._model = model or config.model

        # Resolve tools from preset + extras
        tool_names = list(resolved_preset.tools)
        if config.extra_tools:
            for t in config.extra_tools:
                if t not in tool_names:
                    tool_names.append(t)

        tools = get_tools(tool_names)
        if extra_tools:
            tools.extend(extra_tools)

        self._tools = tools

        # Resolve system prompt
        self._system_prompt = system_prompt or resolved_preset.system_prompt

        # Resolve provider
        if provider is None:
            provider = ProxyProvider(
                model=self._model,
                base_url=config.provider.base_url,
                api_key=config.provider.api_key,
            )
        self._provider = provider

        # Create the underlying isotope-core Agent
        self._agent = Agent(
            provider=provider,
            system_prompt=self._system_prompt,
            tools=tools,
            **agent_kwargs,
        )

    @property
    def agent(self) -> Agent:
        """Access the underlying isotope-core Agent."""
        return self._agent

    @property
    def preset(self) -> Preset:
        """Get the active preset."""
        return self._preset

    @property
    def model(self) -> str:
        """Get the active model name."""
        return self._model

    @property
    def config(self) -> IsotopeConfig:
        """Get the configuration."""
        return self._config

    @property
    def tools(self) -> list[Tool]:
        """Get the active tools."""
        return self._tools

    def set_model(self, model: str) -> None:
        """Switch the model by rebuilding the provider.

        Args:
            model: New model name.
        """
        self._model = model
        new_provider = ProxyProvider(
            model=model,
            base_url=self._config.provider.base_url,
            api_key=self._config.provider.api_key,
        )
        self._provider = new_provider
        self._agent.set_provider(new_provider)

    def set_system_prompt(self, prompt: str) -> None:
        """Update the system prompt.

        Args:
            prompt: New system prompt text.
        """
        self._system_prompt = prompt
        self._agent.set_system_prompt(prompt)

    def set_tools_enabled(self, enabled: bool) -> None:
        """Enable or disable tools.

        Args:
            enabled: If True, use preset tools. If False, clear all tools.
        """
        if enabled:
            self._agent.set_tools(self._tools)
        else:
            self._agent.set_tools([])
