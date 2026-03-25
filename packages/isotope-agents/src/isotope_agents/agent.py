"""IsotopeAgent — high-level agent wrapping isotope-core with presets."""

from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncGenerator

from isotope_core import Agent
from isotope_core.context import FileTracker
from isotope_core.providers.base import Provider
from isotope_core.tools import Tool
from isotope_core.types import UserMessage, AgentEvent, TurnEndEvent, TextContent

from isotope_agents.compaction import CompactionResult, compact_messages, _estimate_messages_tokens
from isotope_agents.presets import Preset, get_preset
from isotope_agents.session import SessionStore

logger = logging.getLogger(__name__)

_DEFAULT_CONTEXT_WINDOW = 128_000
_COMPACTION_THRESHOLD = 0.80  # 80% of context window


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
        context_window: int = _DEFAULT_CONTEXT_WINDOW,
        file_tracker: FileTracker | None = None,
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
            context_window: Context window size in tokens (default 128000).
            file_tracker: FileTracker instance for tracking file operations.
                If not provided, one is created automatically.
        """
        self._workspace = workspace or os.getcwd()

        # Store session persistence components
        self._session_store = session_store
        self._session_id = session_id

        # Compaction support
        self._provider = provider
        self._context_window = context_window
        self._file_tracker = file_tracker or FileTracker()

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

        # After the turn completes, check if auto-compaction is needed
        await self._maybe_auto_compact()

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

    async def _maybe_auto_compact(self) -> CompactionResult | None:
        """Check if auto-compaction should be triggered and perform it if so.

        Compaction is triggered when the estimated token count exceeds
        80% of the context window.

        Returns:
            CompactionResult if compaction was performed, None otherwise.
        """
        messages = self._agent.messages
        if not messages:
            return None

        estimated_tokens = _estimate_messages_tokens(messages)
        threshold = int(self._context_window * _COMPACTION_THRESHOLD)

        if estimated_tokens <= threshold:
            return None

        logger.info(
            "Auto-compaction triggered: ~%d tokens > %d threshold",
            estimated_tokens,
            threshold,
        )
        return await self.compact()

    async def compact(self) -> CompactionResult:
        """Manually trigger compaction of the conversation history.

        Compacts older messages into a summary, preserving recent context
        and file operation metadata. Replaces the agent's message history
        with a summary message plus the most recent messages.

        Returns:
            CompactionResult with summary text, file lists, and token stats.
        """
        messages = self._agent.messages

        result = await compact_messages(
            messages=messages,
            provider=self._provider,
            file_tracker=self._file_tracker,
        )

        if result.summary and result.messages_compacted > 0:
            # Build new message list: summary as a system-like user message + kept messages
            summary_msg = UserMessage(
                content=[TextContent(text=f"[Compacted conversation summary]\n{result.summary}")],
                timestamp=int(time.time() * 1000),
                pinned=True,
            )

            # Keep the last N messages (same as keep_last_n default = 4)
            keep_last_n = 4
            if len(messages) > keep_last_n:
                kept_messages = messages[-keep_last_n:]
            else:
                kept_messages = list(messages)

            new_messages = [summary_msg] + kept_messages
            self._agent.replace_messages(new_messages)

            # Store compaction entry to session if persistence enabled
            if self._session_store and self._session_id:
                from isotope_agents.session import SessionEntry
                from datetime import datetime, timezone

                compaction_entry = SessionEntry(
                    type="compaction",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    data={
                        "summary": result.summary,
                        "files_read": result.files_read,
                        "files_modified": result.files_modified,
                        "messages_compacted": result.messages_compacted,
                        "tokens_before": result.tokens_before,
                        "tokens_after": result.tokens_after,
                    },
                )
                self._session_store.append(self._session_id, compaction_entry)

        return result

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

    @property
    def file_tracker(self) -> FileTracker:
        """The file tracker for this agent."""
        return self._file_tracker

    @property
    def context_window(self) -> int:
        """The context window size in tokens."""
        return self._context_window
