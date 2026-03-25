"""IsotopeAgent — high-level agent wrapping isotope-core with presets.

Provides a convenient interface for creating agents with preset-based
tool registration and system prompts, with optional session persistence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from isotope_core import Agent
from isotope_core.providers.base import Provider
from isotope_core.providers.proxy import ProxyProvider
from isotope_core.tools import Tool

from isotope_agents.config import IsotopeConfig
from isotope_agents.presets import PRESETS, Preset
from isotope_agents.session import Session, SessionStore
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
        session_id: str | None = None,
        sessions_dir: str | Path | None = None,
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
            session_id: If provided, load this session and restore messages.
            sessions_dir: Custom sessions directory for SessionStore.
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

        # Session support
        self._session_store = SessionStore(sessions_dir=sessions_dir)
        self._session: Session | None = None

        if session_id is not None:
            self.load_session(session_id)

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

    @property
    def session(self) -> Session | None:
        """Get the current session, if any."""
        return self._session

    @property
    def session_store(self) -> SessionStore:
        """Get the session store."""
        return self._session_store

    def new_session(self) -> Session:
        """Create a new session and associate it with this agent.

        If there's an existing session, saves it first.

        Returns:
            The newly created Session.
        """
        if self._session is not None:
            self.save_session()

        self._session = Session(
            preset=self._preset.name,
            model=self._model,
        )
        self._agent.clear_messages()
        return self._session

    def load_session(self, session_id: str) -> Session:
        """Load a session from disk and restore its messages.

        If there's an existing session, saves it first.

        Args:
            session_id: UUID of the session to load.

        Returns:
            The loaded Session.

        Raises:
            FileNotFoundError: If the session doesn't exist.
            ValueError: If the session data is invalid.
        """
        if self._session is not None:
            self.save_session()

        session = self._session_store.load(session_id)
        self._session = session

        # Restore messages into the isotope-core agent
        self._agent.clear_messages()
        for msg in session.messages:
            self._agent.append_message(msg)

        return session

    def save_session(self) -> Path | None:
        """Save the current session to disk.

        Syncs agent messages into the session before saving.

        Returns:
            Path to the saved file, or None if no session is active.
        """
        if self._session is None:
            return None

        # Sync messages from agent into session
        self._session.messages = list(self._agent.messages)
        return self._session_store.save(self._session)

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
