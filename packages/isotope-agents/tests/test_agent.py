"""Tests for IsotopeAgent."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from isotope_agents.agent import IsotopeAgent
from isotope_agents.presets import ASSISTANT
from isotope_agents.session import SessionStore


class TestIsotopeAgent:
    """Tests for IsotopeAgent initialization and configuration."""

    def _mock_provider(self) -> MagicMock:
        """Create a mock provider."""
        provider = MagicMock()
        provider.stream = AsyncMock()
        return provider

    def test_default_preset_is_coding(self) -> None:
        """Default preset should be coding."""
        agent = IsotopeAgent(provider=self._mock_provider())
        assert agent.preset.name == "coding"
        tool_names = {t.name for t in agent.tools}
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "bash" in tool_names
        assert "grep" in tool_names

    def test_assistant_preset(self) -> None:
        """Assistant preset excludes write/edit."""
        agent = IsotopeAgent(
            provider=self._mock_provider(), preset="assistant"
        )
        assert agent.preset.name == "assistant"
        tool_names = {t.name for t in agent.tools}
        assert "write_file" not in tool_names
        assert "edit_file" not in tool_names

    def test_minimal_preset(self) -> None:
        """Minimal preset has bash only."""
        agent = IsotopeAgent(
            provider=self._mock_provider(), preset="minimal"
        )
        tool_names = {t.name for t in agent.tools}
        assert tool_names == {"bash"}

    def test_preset_instance(self) -> None:
        """Accept Preset instance directly."""
        agent = IsotopeAgent(
            provider=self._mock_provider(), preset=ASSISTANT
        )
        assert agent.preset is ASSISTANT

    def test_custom_system_prompt(self) -> None:
        """Custom system prompt overrides preset."""
        agent = IsotopeAgent(
            provider=self._mock_provider(),
            system_prompt="Custom prompt",
        )
        assert agent.core._state.system_prompt == "Custom prompt"

    def test_extra_tools(self) -> None:
        """Extra tools are added to preset tools."""
        from isotope_core.tools import auto_tool

        @auto_tool
        async def custom_tool(x: str) -> str:
            """A custom tool.

            Args:
                x: Input.
            """
            return x

        agent = IsotopeAgent(
            provider=self._mock_provider(),
            preset="minimal",
            extra_tools=[custom_tool],
        )
        tool_names = {t.name for t in agent.tools}
        assert "custom_tool" in tool_names
        assert "bash" in tool_names

    def test_workspace_setting(self) -> None:
        """Workspace is set on the agent."""
        agent = IsotopeAgent(
            provider=self._mock_provider(),
            workspace="/test/workspace",
        )
        assert agent.workspace == "/test/workspace"

    def test_invalid_preset_name(self) -> None:
        """Invalid preset name raises KeyError."""
        with pytest.raises(KeyError):
            IsotopeAgent(
                provider=self._mock_provider(), preset="nonexistent"
            )

    def test_core_property(self) -> None:
        """Core property exposes the underlying Agent."""
        from isotope_core import Agent

        agent = IsotopeAgent(provider=self._mock_provider())
        assert isinstance(agent.core, Agent)

    def test_session_persistence_without_store(self) -> None:
        """Agent works without session persistence."""
        agent = IsotopeAgent(provider=self._mock_provider())
        assert agent.session_id is None

    def test_session_creation_with_store(self) -> None:
        """Agent creates new session when SessionStore provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_store = SessionStore(Path(tmpdir))
            agent = IsotopeAgent(
                provider=self._mock_provider(),
                preset="coding",
                model="test-model",
                session_store=session_store,
            )

            assert agent.session_id is not None
            assert len(agent.session_id) == 8

            # Verify session_start entry was created
            entries = session_store.load(agent.session_id)
            assert len(entries) == 1
            assert entries[0].type == "session_start"
            assert entries[0].data["model"] == "test-model"
            assert entries[0].data["preset"] == "coding"

    def test_session_resume_with_existing_id(self) -> None:
        """Agent loads existing session when session_id provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_store = SessionStore(Path(tmpdir))

            # Create initial session
            session_id = session_store.create("test-model", "coding")

            # Create agent with existing session_id
            agent = IsotopeAgent(
                provider=self._mock_provider(),
                preset="coding",
                model="test-model",
                session_store=session_store,
                session_id=session_id,
            )

            assert agent.session_id == session_id
            # Should have loaded the existing session (only one session_start entry)
            entries = session_store.load(session_id)
            assert len(entries) == 1
            assert entries[0].type == "session_start"

    def test_session_resume_with_nonexistent_id(self) -> None:
        """Agent creates new session when provided session_id doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            session_store = SessionStore(Path(tmpdir))

            # Try to create agent with non-existent session_id
            agent = IsotopeAgent(
                provider=self._mock_provider(),
                preset="coding",
                model="test-model",
                session_store=session_store,
                session_id="nonexist",
            )

            # Should have created a new session (different from "nonexist")
            assert agent.session_id is not None
            assert agent.session_id != "nonexist"
            assert len(agent.session_id) == 8

    @pytest.mark.asyncio
    async def test_session_event_logging(self) -> None:
        """Agent logs events to session during execution."""
        from isotope_core.types import TurnEndEvent, AssistantMessage, Usage

        with tempfile.TemporaryDirectory() as tmpdir:
            session_store = SessionStore(Path(tmpdir))

            # Mock the provider to return a simple event stream
            provider = self._mock_provider()

            # Create a mock turn end event
            mock_message = AssistantMessage(
                content=[],
                usage=Usage(input_tokens=10, output_tokens=5),
                timestamp=1000,
            )
            mock_event = TurnEndEvent(
                message=mock_message,
                tool_results=[],
            )

            async def mock_run(*args, **kwargs):
                yield mock_event

            provider.stream = AsyncMock()

            # Create agent with session store
            agent = IsotopeAgent(
                provider=provider,
                preset="minimal",
                model="test-model",
                session_store=session_store,
            )

            # Mock the core agent's run method
            agent.core.run = mock_run

            # Run the agent (this should log the user message and assistant response)
            events = []
            async for event in agent.run("test message"):
                events.append(event)

            # Check that events were captured
            assert len(events) == 1
            assert events[0] == mock_event

            # Check session entries were logged
            entries = session_store.load(agent.session_id)
            # Should have: session_start, user_message, assistant_message
            assert len(entries) == 3
            assert entries[0].type == "session_start"
            assert entries[1].type == "user_message"
            assert entries[2].type == "assistant_message"
