"""Tests for session persistence functionality."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from isotope_agents.session import SessionEntry, SessionStore
from isotope_core.types import (
    AssistantMessage,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolResultMessage,
    Usage,
    UserMessage,
)


class TestSessionStore:
    """Tests for SessionStore functionality."""

    def test_create_session(self, tmp_path: Path) -> None:
        """Test create session creates file and writes session_start entry."""
        store = SessionStore(sessions_dir=tmp_path)

        session_id = store.create(model="claude-3-5-sonnet", preset="coding")

        # Verify session ID format
        assert len(session_id) == 8
        assert session_id.isalnum()

        # Verify session file was created
        session_file = tmp_path / f"{session_id}.jsonl"
        assert session_file.exists()

        # Verify session_start entry was written
        entries = store.load(session_id)
        assert len(entries) == 1
        assert entries[0].type == "session_start"
        assert entries[0].data["model"] == "claude-3-5-sonnet"
        assert entries[0].data["preset"] == "coding"

    def test_append_and_load_round_trip(self, tmp_path: Path) -> None:
        """Test appending entries and loading them back."""
        store = SessionStore(sessions_dir=tmp_path)
        session_id = store.create(model="test-model", preset="test-preset")

        # Create test entries
        user_entry = SessionEntry(
            type="user_message",
            timestamp=datetime.now(timezone.utc).isoformat(),
            data={
                "content": [{"type": "text", "text": "Hello, world!"}],
                "pinned": False,
            },
        )

        assistant_entry = SessionEntry(
            type="assistant_message",
            timestamp=datetime.now(timezone.utc).isoformat(),
            data={
                "content": [{"type": "text", "text": "Hello! How can I help you?"}],
                "stop_reason": "end_turn",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 15,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                },
                "error_message": None,
                "pinned": False,
            },
        )

        # Append entries
        store.append(session_id, user_entry)
        store.append(session_id, assistant_entry)

        # Load and verify
        entries = store.load(session_id)
        assert len(entries) == 3  # session_start + user_message + assistant_message

        # Verify user message entry
        user_loaded = entries[1]
        assert user_loaded.type == "user_message"
        assert user_loaded.data["content"][0]["text"] == "Hello, world!"

        # Verify assistant message entry
        assistant_loaded = entries[2]
        assert assistant_loaded.type == "assistant_message"
        assert (
            assistant_loaded.data["content"][0]["text"] == "Hello! How can I help you?"
        )
        assert assistant_loaded.data["usage"]["input_tokens"] == 10

    def test_list_sessions(self, tmp_path: Path) -> None:
        """Test list_sessions returns correct metadata."""
        store = SessionStore(sessions_dir=tmp_path)

        # Create first session
        session_id1 = store.create(model="model1", preset="preset1")
        store.append(
            session_id1,
            SessionEntry(
                type="user_message",
                timestamp=datetime.now(timezone.utc).isoformat(),
                data={
                    "content": [{"type": "text", "text": "First message"}],
                    "pinned": False,
                },
            ),
        )

        # Create second session
        session_id2 = store.create(model="model2", preset="preset2")
        store.append(
            session_id2,
            SessionEntry(
                type="user_message",
                timestamp=datetime.now(timezone.utc).isoformat(),
                data={
                    "content": [
                        {
                            "type": "text",
                            "text": "Second message with longer text content",
                        }
                    ],
                    "pinned": False,
                },
            ),
        )

        # List sessions
        sessions = store.list_sessions()

        assert len(sessions) == 2

        # Sessions should be sorted by start time (newest first)
        assert sessions[0].id == session_id2
        assert sessions[1].id == session_id1

        # Verify metadata
        session1_meta = next(s for s in sessions if s.id == session_id1)
        assert session1_meta.model == "model1"
        assert session1_meta.preset == "preset1"
        assert session1_meta.message_count == 1
        assert session1_meta.last_message_preview == "First message"

        session2_meta = next(s for s in sessions if s.id == session_id2)
        assert session2_meta.model == "model2"
        assert session2_meta.preset == "preset2"
        assert session2_meta.message_count == 1
        assert (
            "Second message with longer text content"
            in session2_meta.last_message_preview
        )

    def test_entries_to_messages_conversion(self, tmp_path: Path) -> None:
        """Test entries_to_messages converts back to isotope-core message objects."""
        store = SessionStore(sessions_dir=tmp_path)

        # Create original messages
        user_msg = UserMessage(
            content=[TextContent(text="Test user message")],
            timestamp=1234567890000,
            pinned=False,
        )

        assistant_msg = AssistantMessage(
            content=[
                TextContent(text="Test response"),
                ToolCallContent(
                    id="call_123", name="test_tool", arguments={"arg1": "value1"}
                ),
            ],
            usage=Usage(input_tokens=10, output_tokens=20),
            timestamp=1234567890001,
            pinned=False,
        )

        tool_result_msg = ToolResultMessage(
            tool_call_id="call_123",
            tool_name="test_tool",
            content=[TextContent(text="Tool result")],
            is_error=False,
            timestamp=1234567890002,
            pinned=False,
        )

        # Convert to entries and back
        user_entry = store.message_to_entry(user_msg)
        assistant_entry = store.message_to_entry(assistant_msg)
        tool_result_entry = store.message_to_entry(tool_result_msg)

        entries = [user_entry, assistant_entry, tool_result_entry]
        messages = store.entries_to_messages(entries)

        assert len(messages) == 3

        # Verify user message
        restored_user = messages[0]
        assert isinstance(restored_user, UserMessage)
        assert restored_user.content[0].text == "Test user message"

        # Verify assistant message
        restored_assistant = messages[1]
        assert isinstance(restored_assistant, AssistantMessage)
        assert restored_assistant.content[0].text == "Test response"
        assert restored_assistant.content[1].name == "test_tool"
        assert restored_assistant.usage.input_tokens == 10

        # Verify tool result message
        restored_tool_result = messages[2]
        assert isinstance(restored_tool_result, ToolResultMessage)
        assert restored_tool_result.tool_call_id == "call_123"
        assert restored_tool_result.tool_name == "test_tool"
        assert restored_tool_result.content[0].text == "Tool result"

    def test_load_nonexistent_session_raises_error(self, tmp_path: Path) -> None:
        """Test loading nonexistent session raises FileNotFoundError."""
        store = SessionStore(sessions_dir=tmp_path)

        with pytest.raises(FileNotFoundError, match="Session nonexistent not found"):
            store.load("nonexistent")

    def test_empty_session_directory_returns_empty_list(self, tmp_path: Path) -> None:
        """Test empty session directory returns empty list."""
        store = SessionStore(sessions_dir=tmp_path)

        sessions = store.list_sessions()
        assert sessions == []

    def test_corrupted_session_file_skipped_in_list(self, tmp_path: Path) -> None:
        """Test corrupted session files are skipped when listing sessions."""
        store = SessionStore(sessions_dir=tmp_path)

        # Create valid session
        session_id = store.create(model="test-model", preset="test-preset")

        # Create corrupted session file
        corrupted_file = tmp_path / "corrupted.jsonl"
        with open(corrupted_file, "w") as f:
            f.write("invalid json content\n")

        # List sessions should only return the valid one
        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].id == session_id

    def test_session_with_thinking_content(self, tmp_path: Path) -> None:
        """Test session handling with thinking content blocks."""
        store = SessionStore(sessions_dir=tmp_path)

        # Create message with thinking content
        msg = AssistantMessage(
            content=[
                ThinkingContent(
                    thinking="I need to think about this...",
                    thinking_signature="test_signature",
                    redacted=False,
                ),
                TextContent(text="Here's my response"),
            ],
            usage=Usage(),
            timestamp=1234567890000,
            pinned=False,
        )

        # Convert and back
        entry = store.message_to_entry(msg)
        restored_msgs = store.entries_to_messages([entry])

        assert len(restored_msgs) == 1
        restored = restored_msgs[0]
        assert isinstance(restored, AssistantMessage)
        assert len(restored.content) == 2

        thinking_block = restored.content[0]
        assert isinstance(thinking_block, ThinkingContent)
        assert thinking_block.thinking == "I need to think about this..."
        assert thinking_block.thinking_signature == "test_signature"
        assert thinking_block.redacted is False

    def test_message_preview_truncation(self, tmp_path: Path) -> None:
        """Test message preview is truncated when too long."""
        store = SessionStore(sessions_dir=tmp_path)

        session_id = store.create(model="test-model", preset="test-preset")

        # Create long message
        long_text = "A" * 150  # Longer than 100 chars
        store.append(
            session_id,
            SessionEntry(
                type="user_message",
                timestamp=datetime.now(timezone.utc).isoformat(),
                data={
                    "content": [{"type": "text", "text": long_text}],
                    "pinned": False,
                },
            ),
        )

        sessions = store.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].last_message_preview.endswith("...")
        assert len(sessions[0].last_message_preview) == 103  # 100 chars + "..."

    def test_default_sessions_directory(self) -> None:
        """Test default sessions directory is ~/.isotope/sessions."""
        store = SessionStore()
        expected = Path.home() / ".isotope" / "sessions"
        assert store.sessions_dir == expected

    def test_multiple_content_blocks_in_message(self, tmp_path: Path) -> None:
        """Test messages with multiple content blocks."""
        store = SessionStore(sessions_dir=tmp_path)

        # Create message with multiple text blocks
        msg = UserMessage(
            content=[
                TextContent(text="First part"),
                TextContent(text="Second part"),
            ],
            timestamp=1234567890000,
            pinned=False,
        )

        # Convert and back
        entry = store.message_to_entry(msg)
        restored_msgs = store.entries_to_messages([entry])

        assert len(restored_msgs) == 1
        restored = restored_msgs[0]
        assert isinstance(restored, UserMessage)
        assert len(restored.content) == 2
        assert restored.content[0].text == "First part"
        assert restored.content[1].text == "Second part"

    def test_compaction_entry_round_trip(self, tmp_path: Path) -> None:
        """Test compaction entry can be written, read, and converted to messages."""
        store = SessionStore(sessions_dir=tmp_path)
        session_id = store.create(model="test-model", preset="test-preset")

        # Create a compaction entry
        compaction_entry = SessionEntry(
            type="compaction",
            timestamp=datetime.now(timezone.utc).isoformat(),
            data={
                "summary": "User asked to write a hello world script. Assistant created hello.py.",
                "files_read": ["hello.py", "README.md"],
                "files_modified": ["hello.py"],
                "messages_compacted": 8,
                "tokens_before": 5000,
                "tokens_after": 500,
            },
        )

        # Append to session
        store.append(session_id, compaction_entry)

        # Load back
        entries = store.load(session_id)
        assert len(entries) == 2  # session_start + compaction
        assert entries[1].type == "compaction"
        assert (
            entries[1].data["summary"]
            == "User asked to write a hello world script. Assistant created hello.py."
        )
        assert entries[1].data["files_read"] == ["hello.py", "README.md"]
        assert entries[1].data["files_modified"] == ["hello.py"]
        assert entries[1].data["messages_compacted"] == 8
        assert entries[1].data["tokens_before"] == 5000
        assert entries[1].data["tokens_after"] == 500

        # Convert to messages — compaction should become a pinned UserMessage
        messages = store.entries_to_messages(entries)
        assert (
            len(messages) == 1
        )  # only the compaction entry becomes a message (session_start is skipped)

        compaction_msg = messages[0]
        assert isinstance(compaction_msg, UserMessage)
        assert compaction_msg.pinned is True
        assert "[Compacted conversation summary]" in compaction_msg.content[0].text
        assert "hello world script" in compaction_msg.content[0].text

    def test_compaction_entry_empty_summary_skipped(self, tmp_path: Path) -> None:
        """Test compaction entry with empty summary is not converted to a message."""
        store = SessionStore(sessions_dir=tmp_path)

        compaction_entry = SessionEntry(
            type="compaction",
            timestamp=datetime.now(timezone.utc).isoformat(),
            data={
                "summary": "",
                "files_read": [],
                "files_modified": [],
                "messages_compacted": 0,
                "tokens_before": 0,
                "tokens_after": 0,
            },
        )

        messages = store.entries_to_messages([compaction_entry])
        assert len(messages) == 0
