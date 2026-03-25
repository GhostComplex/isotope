"""Tests for session integration with Agent, TUI, and CLI."""

from __future__ import annotations

import tempfile
import time

import pytest
from click.testing import CliRunner
from isotope_core.types import TextContent, UserMessage

from isotope_agents.agent import IsotopeAgent
from isotope_agents.cli import main
from isotope_agents.config import IsotopeConfig
from isotope_agents.session import Session, SessionStore

# ============================================================================
# Helper factories
# ============================================================================


def _make_config() -> IsotopeConfig:
    """Create a default config for testing."""
    return IsotopeConfig()


def _make_agent(
    sessions_dir: str | None = None,
    session_id: str | None = None,
) -> IsotopeAgent:
    """Create an IsotopeAgent with session support for testing."""
    return IsotopeAgent(
        preset="minimal",
        config=_make_config(),
        sessions_dir=sessions_dir,
        session_id=session_id,
    )


def _seed_session(store: SessionStore, session_id: str = "test-seed-001") -> Session:
    """Save a session with some messages and return it."""
    session = Session(
        id=session_id,
        name="Seeded Session",
        preset="minimal",
        model="claude-opus-4.6",
        messages=[
            UserMessage(
                content=[TextContent(text="Hello from seed")],
                timestamp=int(time.time()),
            ),
        ],
    )
    store.save(session)
    return session


# ============================================================================
# IsotopeAgent session integration
# ============================================================================


class TestAgentSessionIntegration:
    """Test session methods on IsotopeAgent."""

    def test_new_session_creates_session(self) -> None:
        """new_session() creates and returns a Session."""
        agent = _make_agent()
        session = agent.new_session()
        assert session is not None
        assert session.preset == "minimal"
        assert session.message_count == 0
        assert agent.session is session

    def test_new_session_clears_messages(self) -> None:
        """new_session() clears the agent's message history."""
        agent = _make_agent()
        # Manually add a message
        agent.agent.append_message(
            UserMessage(
                content=[TextContent(text="old")],
                timestamp=int(time.time()),
            )
        )
        assert len(agent.agent.messages) == 1

        agent.new_session()
        assert len(agent.agent.messages) == 0

    def test_save_session(self) -> None:
        """save_session() persists the session to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = _make_agent(sessions_dir=tmpdir)
            session = agent.new_session()

            # Add a message through the agent
            agent.agent.append_message(
                UserMessage(
                    content=[TextContent(text="Test message")],
                    timestamp=int(time.time()),
                )
            )

            path = agent.save_session()
            assert path is not None
            assert path.exists()

            # Verify saved content
            loaded = agent.session_store.load(session.id)
            assert loaded.message_count == 1

    def test_save_session_no_session(self) -> None:
        """save_session() returns None when no session is active."""
        agent = _make_agent()
        assert agent.save_session() is None

    def test_load_session(self) -> None:
        """load_session() restores session and messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            seeded = _seed_session(store)

            agent = _make_agent(sessions_dir=tmpdir)
            loaded = agent.load_session(seeded.id)

            assert loaded.id == seeded.id
            assert agent.session is loaded
            assert len(agent.agent.messages) == 1

    def test_load_session_via_constructor(self) -> None:
        """session_id in constructor loads the session automatically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            seeded = _seed_session(store)

            agent = _make_agent(sessions_dir=tmpdir, session_id=seeded.id)
            assert agent.session is not None
            assert agent.session.id == seeded.id
            assert len(agent.agent.messages) == 1

    def test_load_nonexistent_session_raises(self) -> None:
        """Loading a nonexistent session raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = _make_agent(sessions_dir=tmpdir)
            with pytest.raises(FileNotFoundError):
                agent.load_session("nonexistent")

    def test_new_session_saves_current_first(self) -> None:
        """new_session() saves the current session before creating a new one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = _make_agent(sessions_dir=tmpdir)
            first = agent.new_session()
            first_id = first.id

            # Add a message
            agent.agent.append_message(
                UserMessage(
                    content=[TextContent(text="Should be saved")],
                    timestamp=int(time.time()),
                )
            )

            # Create new session (should auto-save first)
            agent.new_session()

            # Verify first session was saved
            loaded = agent.session_store.load(first_id)
            assert loaded.message_count == 1

    def test_load_session_saves_current_first(self) -> None:
        """load_session() saves the current session before switching."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            seeded = _seed_session(store)

            agent = _make_agent(sessions_dir=tmpdir)
            first = agent.new_session()
            first_id = first.id

            agent.agent.append_message(
                UserMessage(
                    content=[TextContent(text="Will be saved")],
                    timestamp=int(time.time()),
                )
            )

            # Switch to seeded session
            agent.load_session(seeded.id)

            # Verify first session was saved
            loaded = agent.session_store.load(first_id)
            assert loaded.message_count == 1

    def test_session_store_property(self) -> None:
        """session_store property returns the SessionStore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = _make_agent(sessions_dir=tmpdir)
            assert agent.session_store is not None
            assert agent.session_store.sessions_dir.as_posix() == tmpdir


# ============================================================================
# CLI integration tests
# ============================================================================


class TestCLISessionIntegration:
    """Test session-related CLI commands."""

    def test_sessions_command_empty(self) -> None:
        """isotope sessions shows message when no sessions exist."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["sessions"])
            assert result.exit_code == 0
            assert "No saved sessions" in result.output

    def test_sessions_command_with_data(self) -> None:
        """isotope sessions lists saved sessions."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            _seed_session(store, "test-list-001")

            # Patch the default store to use tmpdir
            import isotope_agents.session as session_module

            original_default = session_module.DEFAULT_SESSIONS_DIR
            try:
                session_module.DEFAULT_SESSIONS_DIR = tmpdir  # type: ignore[assignment]
                result = runner.invoke(main, ["sessions"])
                assert result.exit_code == 0
                assert "test-list-001" in result.output
            finally:
                session_module.DEFAULT_SESSIONS_DIR = original_default

    def test_sessions_delete(self) -> None:
        """isotope sessions --delete removes a session."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            _seed_session(store, "delete-me-001")

            import isotope_agents.session as session_module

            original_default = session_module.DEFAULT_SESSIONS_DIR
            try:
                session_module.DEFAULT_SESSIONS_DIR = tmpdir  # type: ignore[assignment]
                result = runner.invoke(main, ["sessions", "--delete", "delete-me-001"])
                assert result.exit_code == 0
                assert "Deleted" in result.output
                assert not store.exists("delete-me-001")
            finally:
                session_module.DEFAULT_SESSIONS_DIR = original_default

    def test_sessions_delete_nonexistent(self) -> None:
        """isotope sessions --delete with bad ID shows error."""
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmpdir:
            import isotope_agents.session as session_module

            original_default = session_module.DEFAULT_SESSIONS_DIR
            try:
                session_module.DEFAULT_SESSIONS_DIR = tmpdir  # type: ignore[assignment]
                result = runner.invoke(main, ["sessions", "--delete", "nonexistent"])
                assert result.exit_code == 1
            finally:
                session_module.DEFAULT_SESSIONS_DIR = original_default

    def test_chat_help_includes_session(self) -> None:
        """Chat command help includes --session option."""
        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert result.exit_code == 0
        assert "--session" in result.output

    def test_sessions_help(self) -> None:
        """Sessions command shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["sessions", "--help"])
        assert result.exit_code == 0
        assert "--delete" in result.output
