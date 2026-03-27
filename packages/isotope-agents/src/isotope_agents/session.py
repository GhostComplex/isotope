"""Session persistence for conversation storage in JSONL format.

This module provides session management functionality for storing and retrieving
conversation data in a structured JSONL format. Sessions are stored in the user's
~/.isotope/sessions/ directory.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from isotope_core.types import (
    AssistantMessage,
    Message,
    ToolResultMessage,
    Usage,
    UserMessage,
    TextContent,
    ImageContent,
    ThinkingContent,
    ToolCallContent,
)


@dataclass
class SessionEntry:
    """One line in a .jsonl session file.

    Each entry represents an event or message in the conversation session.
    """

    type: str          # session_start, user_message, assistant_message, tool_call, tool_result, compaction
    timestamp: str     # ISO 8601
    data: dict[str, Any]         # type-specific payload


@dataclass
class SessionMeta:
    """Metadata for a session.

    Used when listing sessions to provide summary information without loading
    the entire conversation history.
    """

    id: str
    started_at: str  # ISO 8601
    message_count: int
    last_message_preview: str
    model: str
    preset: str


class SessionStore:
    """Manages session persistence in ~/.isotope/sessions/.

    Provides functionality to create new sessions, append messages/events,
    load session history, and list available sessions.
    """

    def __init__(self, sessions_dir: Path | None = None):
        """Initialize session store.

        Args:
            sessions_dir: Custom sessions directory. Defaults to ~/.isotope/sessions
        """
        self.sessions_dir = sessions_dir or Path.home() / ".isotope" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def create(self, model: str, preset: str) -> str:
        """Create a new session, return session ID (8-char short UUID).

        Creates a new session file and writes the initial session_start entry.

        Args:
            model: The model identifier (e.g., "claude-3-5-sonnet")
            preset: The preset name (e.g., "coding", "assistant")

        Returns:
            8-character session ID
        """
        session_id = str(uuid.uuid4()).replace("-", "")[:8]

        # Create the session_start entry
        start_entry = SessionEntry(
            type="session_start",
            timestamp=datetime.now(timezone.utc).isoformat(),
            data={
                "model": model,
                "preset": preset,
            }
        )

        self.append(session_id, start_entry)
        return session_id

    def append(self, session_id: str, entry: SessionEntry) -> None:
        """Append an entry to a session file (atomic append).

        Args:
            session_id: The session identifier
            entry: The entry to append
        """
        session_file = self.sessions_dir / f"{session_id}.jsonl"

        # Convert entry to dict for JSON serialization
        entry_dict = {
            "type": entry.type,
            "timestamp": entry.timestamp,
            "data": entry.data,
        }

        # Atomic append using write + rename for thread safety
        temp_file = session_file.with_suffix(".tmp")

        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(entry_dict) + "\n")

        # If session file already exists, append to it
        if session_file.exists():
            with open(session_file, "r", encoding="utf-8") as existing:
                existing_content = existing.read()

            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(existing_content)
                f.write(json.dumps(entry_dict) + "\n")

        temp_file.replace(session_file)

    def load(self, session_id: str) -> list[SessionEntry]:
        """Load all entries from a session file.

        Args:
            session_id: The session identifier

        Returns:
            List of session entries in chronological order

        Raises:
            FileNotFoundError: If the session file doesn't exist
        """
        session_file = self.sessions_dir / f"{session_id}.jsonl"

        if not session_file.exists():
            raise FileNotFoundError(f"Session {session_id} not found")

        entries = []
        with open(session_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry_dict = json.loads(line)
                    entries.append(SessionEntry(
                        type=entry_dict["type"],
                        timestamp=entry_dict["timestamp"],
                        data=entry_dict["data"],
                    ))

        return entries

    def list_sessions(self) -> list[SessionMeta]:
        """List all sessions with metadata.

        Returns:
            List of session metadata objects, sorted by start time (newest first)
        """
        sessions = []

        for session_file in self.sessions_dir.glob("*.jsonl"):
            session_id = session_file.stem

            try:
                entries = self.load(session_id)
                if not entries:
                    continue

                # Get session start info
                start_entry = next((e for e in entries if e.type == "session_start"), None)
                if not start_entry:
                    continue

                model = start_entry.data.get("model", "unknown")
                preset = start_entry.data.get("preset", "unknown")
                started_at = start_entry.timestamp

                # Count messages and get last message preview
                message_count = len([e for e in entries if e.type in ["user_message", "assistant_message"]])

                # Get last message for preview
                last_message_preview = ""
                for entry in reversed(entries):
                    if entry.type in ["user_message", "assistant_message"]:
                        content = entry.data.get("content", [])
                        if content:
                            # Extract text from first text content block
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", "").strip()
                                    last_message_preview = text[:100] + ("..." if len(text) > 100 else "")
                                    break
                        break

                sessions.append(SessionMeta(
                    id=session_id,
                    started_at=started_at,
                    message_count=message_count,
                    last_message_preview=last_message_preview,
                    model=model,
                    preset=preset,
                ))

            except (json.JSONDecodeError, KeyError, FileNotFoundError):
                # Skip corrupted or invalid session files
                continue

        # Sort by start time (newest first)
        sessions.sort(key=lambda s: s.started_at, reverse=True)
        return sessions

    def entries_to_messages(self, entries: list[SessionEntry]) -> list[Message]:
        """Convert JSONL entries back to isotope-core Message objects for session resume.

        Args:
            entries: List of session entries

        Returns:
            List of Message objects that can be used with isotope-core
        """
        messages = []

        for entry in entries:
            if entry.type == "user_message":
                data = entry.data
                content = []

                for block in data.get("content", []):
                    if block["type"] == "text":
                        content.append(TextContent(text=block["text"]))
                    elif block["type"] == "image":
                        content.append(ImageContent(
                            data=block["data"],
                            mime_type=block["mime_type"]
                        ))

                messages.append(UserMessage(
                    content=content,
                    timestamp=int(datetime.fromisoformat(entry.timestamp.replace('Z', '+00:00')).timestamp() * 1000),
                    pinned=data.get("pinned", False),
                ))

            elif entry.type == "assistant_message":
                data = entry.data
                content = []

                for block in data.get("content", []):
                    if block["type"] == "text":
                        content.append(TextContent(text=block["text"]))
                    elif block["type"] == "thinking":
                        content.append(ThinkingContent(
                            thinking=block["thinking"],
                            thinking_signature=block.get("thinking_signature"),
                            redacted=block.get("redacted", False)
                        ))
                    elif block["type"] == "tool_call":
                        content.append(ToolCallContent(
                            id=block["id"],
                            name=block["name"],
                            arguments=block["arguments"]
                        ))

                usage_data = data.get("usage", {})
                usage = Usage(
                    input_tokens=usage_data.get("input_tokens", 0),
                    output_tokens=usage_data.get("output_tokens", 0),
                    cache_read_tokens=usage_data.get("cache_read_tokens", 0),
                    cache_write_tokens=usage_data.get("cache_write_tokens", 0),
                )

                messages.append(AssistantMessage(
                    content=content,
                    stop_reason=data.get("stop_reason"),
                    usage=usage,
                    error_message=data.get("error_message"),
                    timestamp=int(datetime.fromisoformat(entry.timestamp.replace('Z', '+00:00')).timestamp() * 1000),
                    pinned=data.get("pinned", False),
                ))

            elif entry.type == "tool_result":
                data = entry.data
                content = []

                for block in data.get("content", []):
                    if block["type"] == "text":
                        content.append(TextContent(text=block["text"]))
                    elif block["type"] == "image":
                        content.append(ImageContent(
                            data=block["data"],
                            mime_type=block["mime_type"]
                        ))

                messages.append(ToolResultMessage(
                    tool_call_id=data["tool_call_id"],
                    tool_name=data["tool_name"],
                    content=content,
                    is_error=data.get("is_error", False),
                    timestamp=int(datetime.fromisoformat(entry.timestamp.replace('Z', '+00:00')).timestamp() * 1000),
                    pinned=data.get("pinned", False),
                ))

            elif entry.type == "compaction":
                # Treat compaction entries as system-like user messages
                # with the summary text, so they are replayed on resume.
                data = entry.data
                summary = data.get("summary", "")
                if summary:
                    messages.append(UserMessage(
                        content=[TextContent(
                            text=f"[Compacted conversation summary]\n{summary}",
                        )],
                        timestamp=int(datetime.fromisoformat(entry.timestamp.replace('Z', '+00:00')).timestamp() * 1000),
                        pinned=True,
                    ))

        return messages

    def message_to_entry(self, message: Message) -> SessionEntry:
        """Convert a Message object to a SessionEntry for storage.

        Args:
            message: The message to convert

        Returns:
            SessionEntry ready for storage
        """
        timestamp = datetime.now(timezone.utc).isoformat()

        if isinstance(message, UserMessage):
            content = []
            for block in message.content:
                if isinstance(block, TextContent):
                    content.append({"type": "text", "text": block.text})
                elif isinstance(block, ImageContent):
                    content.append({
                        "type": "image",
                        "data": block.data,
                        "mime_type": block.mime_type
                    })

            return SessionEntry(
                type="user_message",
                timestamp=timestamp,
                data={
                    "content": content,
                    "pinned": message.pinned,
                }
            )

        elif isinstance(message, AssistantMessage):
            content = []
            for block in message.content:
                if isinstance(block, TextContent):
                    content.append({"type": "text", "text": block.text})
                elif isinstance(block, ThinkingContent):
                    content.append({
                        "type": "thinking",
                        "thinking": block.thinking,
                        "thinking_signature": block.thinking_signature,
                        "redacted": block.redacted
                    })
                elif isinstance(block, ToolCallContent):
                    content.append({
                        "type": "tool_call",
                        "id": block.id,
                        "name": block.name,
                        "arguments": block.arguments
                    })

            return SessionEntry(
                type="assistant_message",
                timestamp=timestamp,
                data={
                    "content": content,
                    "stop_reason": message.stop_reason,
                    "usage": {
                        "input_tokens": message.usage.input_tokens,
                        "output_tokens": message.usage.output_tokens,
                        "cache_read_tokens": message.usage.cache_read_tokens,
                        "cache_write_tokens": message.usage.cache_write_tokens,
                    },
                    "error_message": message.error_message,
                    "pinned": message.pinned,
                }
            )

        elif isinstance(message, ToolResultMessage):
            content = []
            for block in message.content:
                if isinstance(block, TextContent):
                    content.append({"type": "text", "text": block.text})
                elif isinstance(block, ImageContent):
                    content.append({
                        "type": "image",
                        "data": block.data,
                        "mime_type": block.mime_type
                    })

            return SessionEntry(
                type="tool_result",
                timestamp=timestamp,
                data={
                    "tool_call_id": message.tool_call_id,
                    "tool_name": message.tool_name,
                    "content": content,
                    "is_error": message.is_error,
                    "pinned": message.pinned,
                }
            )

        else:
            raise ValueError(f"Unsupported message type: {type(message)}")