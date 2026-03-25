"""Tests for session model and persistence."""

from __future__ import annotations

import json
import os
import tempfile
import time

import pytest
from isotope_core.types import (
    AssistantMessage,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolResultMessage,
    Usage,
    UserMessage,
)

from isotope_agents.session import (
    Session,
    SessionStore,
    deserialize_session,
    serialize_session,
)

# ============================================================================
# Helper factories
# ============================================================================


def _make_user_message(text: str = "Hello") -> UserMessage:
    """Create a simple UserMessage for testing."""
    return UserMessage(
        content=[TextContent(text=text)],
        timestamp=int(time.time()),
    )


def _make_assistant_message(text: str = "Hi there!") -> AssistantMessage:
    """Create a simple AssistantMessage for testing."""
    return AssistantMessage(
        content=[TextContent(text=text)],
        usage=Usage(input_tokens=10, output_tokens=20),
        stop_reason="end_turn",
        timestamp=int(time.time()),
    )


def _make_tool_call_message() -> AssistantMessage:
    """Create an AssistantMessage with a tool call."""
    return AssistantMessage(
        content=[
            TextContent(text="Let me check that."),
            ToolCallContent(
                id="call_123",
                name="bash",
                arguments={"command": "echo hello"},
            ),
        ],
        usage=Usage(input_tokens=15, output_tokens=30),
        stop_reason="tool_use",
        timestamp=int(time.time()),
    )


def _make_tool_result_message() -> ToolResultMessage:
    """Create a ToolResultMessage for testing."""
    return ToolResultMessage(
        tool_call_id="call_123",
        tool_name="bash",
        content=[TextContent(text="hello\n")],
        is_error=False,
        timestamp=int(time.time()),
    )


def _make_session_with_messages() -> Session:
    """Create a session with a few messages for testing."""
    return Session(
        id="test-session-001",
        name="Test Session",
        preset="coding",
        model="claude-opus-4.6",
        messages=[
            _make_user_message("Fix the bug in auth.py"),
            _make_assistant_message("I'll look at auth.py for you."),
            _make_tool_call_message(),
            _make_tool_result_message(),
        ],
    )


# ============================================================================
# Session model tests
# ============================================================================


class TestSession:
    """Test Session dataclass."""

    def test_default_session(self) -> None:
        """Session has sensible defaults."""
        session = Session()
        assert len(session.id) == 36  # UUID format
        assert session.name is None
        assert session.preset == "coding"
        assert session.model == "claude-opus-4.6"
        assert session.created_at > 0
        assert session.updated_at > 0
        assert session.messages == []

    def test_message_count(self) -> None:
        """message_count returns the number of messages."""
        session = Session()
        assert session.message_count == 0

        session.messages.append(_make_user_message())
        assert session.message_count == 1

    def test_summary_from_first_user_message(self) -> None:
        """summary returns the first user message text."""
        session = Session(
            messages=[
                _make_user_message("Fix the auth bug"),
                _make_assistant_message("On it!"),
            ]
        )
        assert session.summary == "Fix the auth bug"

    def test_summary_truncation(self) -> None:
        """summary truncates long messages to 80 chars."""
        long_text = "A" * 100
        session = Session(messages=[_make_user_message(long_text)])
        assert len(session.summary) == 80
        assert session.summary.endswith("...")

    def test_summary_empty_session(self) -> None:
        """summary returns '(empty)' for sessions with no user messages."""
        session = Session()
        assert session.summary == "(empty)"

    def test_touch_updates_timestamp(self) -> None:
        """touch() updates the updated_at timestamp."""
        session = Session()
        original = session.updated_at
        time.sleep(0.01)
        session.touch()
        assert session.updated_at > original


# ============================================================================
# Serialization tests
# ============================================================================


class TestSerialization:
    """Test message and session serialization/deserialization."""

    def test_round_trip_simple_messages(self) -> None:
        """Simple user/assistant messages survive serialization round-trip."""
        session = Session(
            id="test-001",
            name="Simple",
            messages=[
                _make_user_message("Hello"),
                _make_assistant_message("Hi there!"),
            ],
        )
        data = serialize_session(session)
        restored = deserialize_session(data)

        assert restored.id == "test-001"
        assert restored.name == "Simple"
        assert len(restored.messages) == 2
        assert isinstance(restored.messages[0], UserMessage)
        assert isinstance(restored.messages[1], AssistantMessage)

        # Verify content
        user_msg = restored.messages[0]
        assert isinstance(user_msg, UserMessage)
        assert user_msg.content[0].text == "Hello"

        assistant_msg = restored.messages[1]
        assert isinstance(assistant_msg, AssistantMessage)
        assert assistant_msg.content[0].text == "Hi there!"
        assert assistant_msg.usage.input_tokens == 10
        assert assistant_msg.usage.output_tokens == 20

    def test_round_trip_tool_messages(self) -> None:
        """Tool call and result messages survive serialization round-trip."""
        session = _make_session_with_messages()
        data = serialize_session(session)
        restored = deserialize_session(data)

        assert len(restored.messages) == 4

        # Check tool call
        tool_call_msg = restored.messages[2]
        assert isinstance(tool_call_msg, AssistantMessage)
        assert len(tool_call_msg.content) == 2
        assert isinstance(tool_call_msg.content[1], ToolCallContent)
        assert tool_call_msg.content[1].name == "bash"
        assert tool_call_msg.content[1].arguments == {"command": "echo hello"}

        # Check tool result
        tool_result_msg = restored.messages[3]
        assert isinstance(tool_result_msg, ToolResultMessage)
        assert tool_result_msg.tool_call_id == "call_123"
        assert tool_result_msg.tool_name == "bash"
        assert not tool_result_msg.is_error

    def test_round_trip_thinking_content(self) -> None:
        """ThinkingContent in messages survives serialization."""
        msg = AssistantMessage(
            content=[
                ThinkingContent(thinking="Let me think...", thinking_signature="sig123"),
                TextContent(text="Here's my answer."),
            ],
            usage=Usage(input_tokens=5, output_tokens=10),
            timestamp=int(time.time()),
        )
        session = Session(id="think-001", messages=[msg])
        data = serialize_session(session)
        restored = deserialize_session(data)

        assert len(restored.messages) == 1
        restored_msg = restored.messages[0]
        assert isinstance(restored_msg, AssistantMessage)
        assert isinstance(restored_msg.content[0], ThinkingContent)
        assert restored_msg.content[0].thinking == "Let me think..."
        assert restored_msg.content[0].thinking_signature == "sig123"

    def test_round_trip_pinned_messages(self) -> None:
        """Pinned flag survives serialization."""
        msg = _make_user_message("Important")
        msg.pinned = True
        session = Session(id="pin-001", messages=[msg])
        data = serialize_session(session)
        restored = deserialize_session(data)

        assert restored.messages[0].pinned is True

    def test_round_trip_json_string(self) -> None:
        """Full JSON string round-trip works."""
        session = _make_session_with_messages()
        data = serialize_session(session)
        json_str = json.dumps(data, indent=2)
        parsed = json.loads(json_str)
        restored = deserialize_session(parsed)

        assert restored.id == session.id
        assert len(restored.messages) == len(session.messages)

    def test_serialization_preserves_metadata(self) -> None:
        """Session metadata (preset, model, timestamps) is preserved."""
        session = Session(
            id="meta-001",
            name="Meta Test",
            preset="assistant",
            model="gpt-4o",
            created_at=1000.0,
            updated_at=2000.0,
        )
        data = serialize_session(session)
        restored = deserialize_session(data)

        assert restored.preset == "assistant"
        assert restored.model == "gpt-4o"
        assert restored.created_at == 1000.0
        assert restored.updated_at == 2000.0

    def test_deserialization_defaults(self) -> None:
        """Deserialization handles missing optional fields gracefully."""
        data = {"id": "default-001", "messages": []}
        session = deserialize_session(data)
        assert session.id == "default-001"
        assert session.name is None
        assert session.preset == "coding"
        assert session.model == "claude-opus-4.6"

    def test_deserialization_error_message(self) -> None:
        """AssistantMessage with error_message deserializes correctly."""
        msg = AssistantMessage(
            content=[TextContent(text="Error occurred")],
            usage=Usage(),
            error_message="Rate limit exceeded",
            timestamp=int(time.time()),
        )
        session = Session(id="err-001", messages=[msg])
        data = serialize_session(session)
        restored = deserialize_session(data)

        restored_msg = restored.messages[0]
        assert isinstance(restored_msg, AssistantMessage)
        assert restored_msg.error_message == "Rate limit exceeded"


# ============================================================================
# SessionStore tests
# ============================================================================


class TestSessionStore:
    """Test SessionStore persistence."""

    def test_save_and_load(self) -> None:
        """Save and load a session round-trips correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            session = _make_session_with_messages()

            path = store.save(session)
            assert path.exists()

            loaded = store.load(session.id)
            assert loaded.id == session.id
            assert loaded.name == session.name
            assert len(loaded.messages) == len(session.messages)

    def test_save_creates_directory(self) -> None:
        """Save auto-creates the sessions directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sessions_dir = os.path.join(tmpdir, "nested", "sessions")
            store = SessionStore(sessions_dir=sessions_dir)
            session = Session(id="create-dir-test")

            store.save(session)
            assert os.path.exists(sessions_dir)

    def test_load_nonexistent_raises(self) -> None:
        """Loading a nonexistent session raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            with pytest.raises(FileNotFoundError, match="Session not found"):
                store.load("nonexistent-id")

    def test_load_corrupt_file_raises(self) -> None:
        """Loading a corrupt JSON file raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)

            # Write invalid JSON
            path = os.path.join(tmpdir, "bad-session.json")
            with open(path, "w") as f:
                f.write("{not valid json}")

            with pytest.raises(ValueError, match="Corrupt session file"):
                store.load("bad-session")

    def test_load_invalid_data_raises(self) -> None:
        """Loading a file with missing required fields raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)

            # Write valid JSON but missing 'id' field
            path = os.path.join(tmpdir, "invalid-data.json")
            with open(path, "w") as f:
                json.dump({"messages": [{"role": "unknown", "content": []}]}, f)

            with pytest.raises(ValueError, match="Invalid session data"):
                store.load("invalid-data")

    def test_list_sessions(self) -> None:
        """list() returns metadata for all saved sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)

            # Save a few sessions
            s1 = Session(
                id="list-001",
                name="First",
                created_at=1000.0,
                updated_at=1000.0,
                messages=[_make_user_message("Hello")],
            )
            s2 = Session(
                id="list-002",
                name="Second",
                created_at=2000.0,
                updated_at=2000.0,
                messages=[
                    _make_user_message("World"),
                    _make_assistant_message("Hi"),
                ],
            )
            store.save(s1)
            store.save(s2)

            listing = store.list()
            assert len(listing) == 2

            # Should be sorted by updated_at descending
            assert listing[0].id == "list-002"
            assert listing[1].id == "list-001"

            # Check metadata
            assert listing[0].name == "Second"
            assert listing[0].message_count == 2
            assert listing[0].summary == "World"

            assert listing[1].name == "First"
            assert listing[1].message_count == 1
            assert listing[1].summary == "Hello"

    def test_list_empty_directory(self) -> None:
        """list() returns empty list when no sessions exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            assert store.list() == []

    def test_list_nonexistent_directory(self) -> None:
        """list() returns empty list when sessions dir doesn't exist."""
        store = SessionStore(sessions_dir="/nonexistent/path")
        assert store.list() == []

    def test_list_skips_corrupt_files(self) -> None:
        """list() silently skips corrupt JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)

            # Save a valid session
            session = Session(
                id="valid-001",
                messages=[_make_user_message("Valid")],
            )
            store.save(session)

            # Write a corrupt file
            corrupt_path = os.path.join(tmpdir, "corrupt.json")
            with open(corrupt_path, "w") as f:
                f.write("not json")

            listing = store.list()
            assert len(listing) == 1
            assert listing[0].id == "valid-001"

    def test_delete_existing(self) -> None:
        """delete() removes the session file and returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            session = Session(id="delete-me")
            store.save(session)
            assert store.exists("delete-me")

            result = store.delete("delete-me")
            assert result is True
            assert not store.exists("delete-me")

    def test_delete_nonexistent(self) -> None:
        """delete() returns False for nonexistent sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            result = store.delete("nonexistent")
            assert result is False

    def test_exists(self) -> None:
        """exists() correctly reports session existence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            assert not store.exists("test-exist")

            session = Session(id="test-exist")
            store.save(session)
            assert store.exists("test-exist")

    def test_multiple_saves_overwrite(self) -> None:
        """Saving a session twice overwrites the file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            session = Session(id="overwrite-001", messages=[])

            store.save(session)
            session.messages.append(_make_user_message("Added later"))
            store.save(session)

            loaded = store.load("overwrite-001")
            assert len(loaded.messages) == 1
            assert isinstance(loaded.messages[0], UserMessage)

    def test_save_updates_timestamp(self) -> None:
        """Saving a session updates its updated_at timestamp."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SessionStore(sessions_dir=tmpdir)
            session = Session(id="ts-001", updated_at=1000.0)

            store.save(session)
            loaded = store.load("ts-001")
            assert loaded.updated_at > 1000.0
