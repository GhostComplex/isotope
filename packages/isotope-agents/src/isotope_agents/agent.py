"""IsotopeAgent — high-level agent wrapping isotope-core with presets."""

from __future__ import annotations

import os
from typing import Any, AsyncGenerator

from isotope_core import Agent
from isotope_core.providers.base import Provider
from isotope_core.tools import Tool
from isotope_core.types import UserMessage, AgentEvent, TurnEndEvent, TextContent

from isotope_agents.presets import Preset, get_preset
from isotope_agents.session import SessionStore


class IsotopeAgent:
    """High-level agent that wraps isotope-core Agent with preset support.

    Usage:
        agent = IsotopeAgent(provider=my_provider)
        async for event in agent.run("Write a hello world script"):
            print(event)

    Or with a specific preset:
        agent = IsotopeAgent(provider=my_provider, preset="assistant")

    Or with custom tools:
        agent = IsotopeAgent(
            provider=my_provider,
            preset="minimal",
            extra_tools=[my_custom_tool],
        )
    """

    def __init__(
        self,
        provider: Provider,
        *,
        preset: str | Preset = "coding",
        model: str | None = None,
        system_prompt: str | None = None,
        extra_tools: list[Tool] | None = None,
        workspace: str | None = None,
        session_id: str | None = None,
        session_store: SessionStore | None = None,
    ) -> None:
        """Initialize the agent.

        Args:
            provider: LLM provider to use.
            preset: Preset name or Preset instance.
            model: Model name (provider-specific).
            system_prompt: Override the preset's system prompt.
            extra_tools: Additional tools beyond the preset's tools.
            workspace: Working directory (defaults to cwd).
            session_id: Existing session ID to resume (requires session_store).
            session_store: Session store for conversation persistence.
        """
        self._workspace = workspace or os.getcwd()

        # Store session persistence components
        self._session_store = session_store
        self._session_id = session_id

        # Resolve preset
        if isinstance(preset, str):
            self._preset = get_preset(preset)
        else:
            self._preset = preset

        # Build system prompt
        if system_prompt:
            self._system_prompt = system_prompt
        else:
            self._system_prompt = self._preset.format_system_prompt(
                cwd=self._workspace
            )

        # Build tool list
        self._tools = list(self._preset.tools)
        if extra_tools:
            self._tools.extend(extra_tools)

        # Patch workspace on tools that need it
        self._patch_tool_workspaces(self._tools)

        # Create the core agent
        self._agent = Agent(
            provider=provider,
            system_prompt=self._system_prompt,
            tools=self._tools,
        )

        # Store model name for reference (used by CLI/TUI)
        self._model = model

        # Handle session persistence
        self._handle_session_persistence()

    def _patch_tool_workspaces(self, tools: list[Tool]) -> None:
        """Set workspace on tools that support it."""
        # Import tool modules and patch their _WORKSPACE
        import isotope_agents.tools.bash as bash_mod
        import isotope_agents.tools.grep as grep_mod
        import isotope_agents.tools.glob as glob_mod
        import isotope_agents.tools.read as read_mod

        bash_mod._WORKSPACE = self._workspace
        grep_mod._WORKSPACE = self._workspace
        glob_mod._WORKSPACE = self._workspace
        read_mod._WORKSPACE = self._workspace

    def _handle_session_persistence(self) -> None:
        """Handle session creation or loading."""
        if self._session_store is not None:
            if self._session_id is None:
                # Create a new session
                model_name = self._model or "unknown"
                self._session_id = self._session_store.create(
                    model=model_name,
                    preset=self._preset.name,
                )
            else:
                # Load existing session and replay messages
                try:
                    entries = self._session_store.load(self._session_id)
                    messages = self._session_store.entries_to_messages(entries)
                    if messages:
                        self._agent.replace_messages(messages)
                except FileNotFoundError:
                    # Session file doesn't exist, create new session
                    model_name = self._model or "unknown"
                    self._session_id = self._session_store.create(
                        model=model_name,
                        preset=self._preset.name,
                    )

    async def run(
        self,
        message: str,
        **kwargs: Any,
    ) -> AsyncGenerator[AgentEvent, None]:
        """Run the agent with a message.

        Args:
            message: User message to process.
            **kwargs: Additional arguments passed to Agent.run().

        Returns:
            The agent's event stream (async iterable of AgentEvent).
        """
        # Store user message to session if persistence enabled
        if self._session_store and self._session_id:
            user_msg = UserMessage(
                content=[TextContent(text=message)],
                timestamp=1000,  # Will be overridden by session store
            )
            entry = self._session_store.message_to_entry(user_msg)
            self._session_store.append(self._session_id, entry)

        # Get the original event stream
        original_stream = self._agent.run(
            messages=[UserMessage(
                content=[TextContent(text=message)],
                timestamp=1000,
            )],
            **kwargs,
        )

        # Wrap the stream to capture session events
        async for event in original_stream:
            # Store relevant events to session
            if self._session_store and self._session_id:
                await self._handle_session_event(event)

            yield event

    async def _handle_session_event(self, event: AgentEvent) -> None:
        """Handle an agent event for session persistence."""
        if not self._session_store or not self._session_id:
            return

        if isinstance(event, TurnEndEvent):
            # Store the assistant message
            entry = self._session_store.message_to_entry(event.message)
            self._session_store.append(self._session_id, entry)

            # Store any tool results
            for tool_result in event.tool_results:
                entry = self._session_store.message_to_entry(tool_result)
                self._session_store.append(self._session_id, entry)

    async def follow_up(self, message: str) -> None:
        """Queue a follow-up message for the agent.

        Args:
            message: Follow-up message text.
        """
        self._agent.follow_up(UserMessage.text(message))

    async def steer(self, message: str) -> None:
        """Steer the agent with a new direction (cancels current stream).

        Args:
            message: Steering message text.
        """
        self._agent.steer(UserMessage.text(message))

    def abort(self) -> None:
        """Abort the current agent execution."""
        self._agent.abort()

    @property
    def preset(self) -> Preset:
        """The current preset."""
        return self._preset

    @property
    def workspace(self) -> str:
        """The workspace directory."""
        return self._workspace

    @property
    def tools(self) -> list[Tool]:
        """The current tool list."""
        return self._tools

    @property
    def core(self) -> Agent:
        """The underlying isotope-core Agent (for advanced use)."""
        return self._agent

    @property
    def session_id(self) -> str | None:
        """The current session ID (if session persistence is enabled)."""
        return self._session_id
