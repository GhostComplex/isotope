"""Session model and persistence for isotope-agents.

Provides the Session data model and SessionStore for saving/loading
conversations to disk as JSON files in ~/.isotope/sessions/.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from isotope_core.types import (
    AssistantMessage,
    ImageContent,
    TextContent,
    ThinkingContent,
    ToolCallContent,
    ToolResultMessage,
    Usage,
    UserMessage,
)

# Type alias for isotope-core message union
Message = UserMessage | AssistantMessage | ToolResultMessage

# Default sessions directory
DEFAULT_SESSIONS_DIR = Path("~/.isotope/sessions")


@dataclass
class Session:
    """A conversation session that can be persisted.

    Attributes:
        id: Unique session identifier (UUID string).
        name: Optional human-readable name for the session.
        preset: Preset name used for this session.
        model: Model name used for this session.
        created_at: Unix timestamp when the session was created.
        updated_at: Unix timestamp when the session was last updated.
        messages: List of isotope-core messages in this session.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str | None = None
    preset: str = "coding"
    model: str = "claude-opus-4.6"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    messages: list[Message] = field(default_factory=list)

    def touch(self) -> None:
        """Update the updated_at timestamp to now."""
        self.updated_at = time.time()

    @property
    def message_count(self) -> int:
        """Return the number of messages in the session."""
        return len(self.messages)

    @property
    def summary(self) -> str:
        """Return a short summary of the session.

        Uses the first user message content as the summary, truncated to 80 chars.
        """
        for msg in self.messages:
            if isinstance(msg, UserMessage):
                for content in msg.content:
                    if isinstance(content, TextContent):
                        text = content.text.strip().replace("\n", " ")
                        if len(text) > 80:
                            return text[:77] + "..."
                        return text
        return "(empty)"


# ============================================================================
# Message serialization
# ============================================================================


def _serialize_content(content: Any) -> dict[str, Any]:
    """Serialize a content block to a JSON-compatible dict."""
    if isinstance(content, TextContent):
        return {"type": "text", "text": content.text}
    if isinstance(content, ImageContent):
        return {"type": "image", "data": content.data, "mime_type": content.mime_type}
    if isinstance(content, ThinkingContent):
        result: dict[str, Any] = {"type": "thinking", "thinking": content.thinking}
        if content.thinking_signature is not None:
            result["thinking_signature"] = content.thinking_signature
        if content.redacted:
            result["redacted"] = True
        return result
    if isinstance(content, ToolCallContent):
        return {
            "type": "tool_call",
            "id": content.id,
            "name": content.name,
            "arguments": content.arguments,
        }
    # Fallback: try model_dump if it's a pydantic model
    if hasattr(content, "model_dump"):
        return content.model_dump()  # type: ignore[no-any-return]
    raise TypeError(f"Unknown content type: {type(content)}")


def _serialize_message(msg: Message) -> dict[str, Any]:
    """Serialize an isotope-core message to a JSON-compatible dict."""
    if isinstance(msg, UserMessage):
        return {
            "role": "user",
            "content": [_serialize_content(c) for c in msg.content],
            "timestamp": msg.timestamp,
            "pinned": msg.pinned,
        }
    if isinstance(msg, AssistantMessage):
        result: dict[str, Any] = {
            "role": "assistant",
            "content": [_serialize_content(c) for c in msg.content],
            "usage": {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "cache_read_tokens": msg.usage.cache_read_tokens,
                "cache_write_tokens": msg.usage.cache_write_tokens,
            },
            "timestamp": msg.timestamp,
            "pinned": msg.pinned,
        }
        if msg.stop_reason is not None:
            result["stop_reason"] = msg.stop_reason
        if msg.error_message is not None:
            result["error_message"] = msg.error_message
        return result
    if isinstance(msg, ToolResultMessage):
        return {
            "role": "tool_result",
            "tool_call_id": msg.tool_call_id,
            "tool_name": msg.tool_name,
            "content": [_serialize_content(c) for c in msg.content],
            "is_error": msg.is_error,
            "timestamp": msg.timestamp,
            "pinned": msg.pinned,
        }
    raise TypeError(f"Unknown message type: {type(msg)}")


def _deserialize_content(data: dict[str, Any]) -> Any:
    """Deserialize a content block from a dict."""
    content_type = data.get("type")
    if content_type == "text":
        return TextContent(text=data["text"])
    if content_type == "image":
        return ImageContent(data=data["data"], mime_type=data["mime_type"])
    if content_type == "thinking":
        return ThinkingContent(
            thinking=data["thinking"],
            thinking_signature=data.get("thinking_signature"),
            redacted=data.get("redacted", False),
        )
    if content_type == "tool_call":
        return ToolCallContent(
            id=data["id"],
            name=data["name"],
            arguments=data["arguments"],
        )
    raise ValueError(f"Unknown content type: {content_type}")


def _deserialize_message(data: dict[str, Any]) -> Message:
    """Deserialize a message from a dict."""
    role = data.get("role")
    if role == "user":
        return UserMessage(
            content=[_deserialize_content(c) for c in data["content"]],
            timestamp=data["timestamp"],
            pinned=data.get("pinned", False),
        )
    if role == "assistant":
        usage_data = data.get("usage", {})
        return AssistantMessage(
            content=[_deserialize_content(c) for c in data["content"]],
            usage=Usage(
                input_tokens=usage_data.get("input_tokens", 0),
                output_tokens=usage_data.get("output_tokens", 0),
                cache_read_tokens=usage_data.get("cache_read_tokens", 0),
                cache_write_tokens=usage_data.get("cache_write_tokens", 0),
            ),
            stop_reason=data.get("stop_reason"),
            error_message=data.get("error_message"),
            timestamp=data["timestamp"],
            pinned=data.get("pinned", False),
        )
    if role == "tool_result":
        return ToolResultMessage(
            tool_call_id=data["tool_call_id"],
            tool_name=data["tool_name"],
            content=[_deserialize_content(c) for c in data["content"]],
            is_error=data.get("is_error", False),
            timestamp=data["timestamp"],
            pinned=data.get("pinned", False),
        )
    raise ValueError(f"Unknown message role: {role}")


# ============================================================================
# Session serialization
# ============================================================================


def serialize_session(session: Session) -> dict[str, Any]:
    """Serialize a Session to a JSON-compatible dict.

    Args:
        session: The session to serialize.

    Returns:
        A dictionary suitable for JSON serialization.
    """
    return {
        "id": session.id,
        "name": session.name,
        "preset": session.preset,
        "model": session.model,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": [_serialize_message(m) for m in session.messages],
    }


def deserialize_session(data: dict[str, Any]) -> Session:
    """Deserialize a Session from a dict.

    Args:
        data: Dictionary from JSON parsing.

    Returns:
        A Session object.

    Raises:
        KeyError: If required fields are missing.
        ValueError: If message data is invalid.
    """
    messages = [_deserialize_message(m) for m in data.get("messages", [])]
    return Session(
        id=data["id"],
        name=data.get("name"),
        preset=data.get("preset", "coding"),
        model=data.get("model", "claude-opus-4.6"),
        created_at=data.get("created_at", 0.0),
        updated_at=data.get("updated_at", 0.0),
        messages=messages,
    )


# ============================================================================
# SessionStore
# ============================================================================


@dataclass
class SessionMetadata:
    """Lightweight session metadata (no messages loaded).

    Used by SessionStore.list() to display session summaries
    without loading the full message history.
    """

    id: str
    name: str | None
    preset: str
    model: str
    created_at: float
    updated_at: float
    message_count: int
    summary: str


class SessionStore:
    """Manages session persistence to disk.

    Sessions are stored as JSON files in the sessions directory,
    one file per session named by UUID.

    Args:
        sessions_dir: Directory to store session files.
            Defaults to ~/.isotope/sessions/.
    """

    def __init__(self, sessions_dir: str | Path | None = None) -> None:
        if sessions_dir is None:
            self._dir = Path(DEFAULT_SESSIONS_DIR).expanduser()
        else:
            self._dir = Path(sessions_dir)

    @property
    def sessions_dir(self) -> Path:
        """Return the sessions directory path."""
        return self._dir

    def _ensure_dir(self) -> None:
        """Create the sessions directory if it doesn't exist."""
        self._dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        """Return the file path for a session ID."""
        return self._dir / f"{session_id}.json"

    def save(self, session: Session) -> Path:
        """Save a session to disk.

        Args:
            session: The session to save.

        Returns:
            Path to the saved file.
        """
        self._ensure_dir()
        session.touch()
        data = serialize_session(session)
        path = self._session_path(session.id)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return path

    def load(self, session_id: str) -> Session:
        """Load a session from disk.

        Args:
            session_id: UUID of the session to load.

        Returns:
            The loaded Session.

        Raises:
            FileNotFoundError: If the session file doesn't exist.
            ValueError: If the session file is corrupt or invalid.
        """
        path = self._session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Corrupt session file: {path}") from exc

        try:
            return deserialize_session(data)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid session data in {path}: {exc}") from exc

    def list(self) -> list[SessionMetadata]:
        """List all saved sessions with metadata (without loading messages).

        Returns:
            List of SessionMetadata sorted by updated_at (newest first).
        """
        if not self._dir.exists():
            return []

        results: list[SessionMetadata] = []
        for path in self._dir.glob("*.json"):
            try:
                text = path.read_text(encoding="utf-8")
                data = json.loads(text)

                # Extract summary from first user message without full deserialization
                summary = "(empty)"
                for msg_data in data.get("messages", []):
                    if msg_data.get("role") == "user":
                        for content_data in msg_data.get("content", []):
                            if content_data.get("type") == "text":
                                text_val = (
                                    content_data["text"].strip().replace("\n", " ")
                                )
                                summary = (
                                    text_val[:77] + "..."
                                    if len(text_val) > 80
                                    else text_val
                                )
                                break
                        if summary != "(empty)":
                            break

                results.append(
                    SessionMetadata(
                        id=data["id"],
                        name=data.get("name"),
                        preset=data.get("preset", "coding"),
                        model=data.get("model", "claude-opus-4.6"),
                        created_at=data.get("created_at", 0.0),
                        updated_at=data.get("updated_at", 0.0),
                        message_count=len(data.get("messages", [])),
                        summary=summary,
                    )
                )
            except (json.JSONDecodeError, KeyError):
                # Skip corrupt files
                continue

        # Sort by updated_at, newest first
        results.sort(key=lambda s: s.updated_at, reverse=True)
        return results

    def delete(self, session_id: str) -> bool:
        """Delete a session file.

        Args:
            session_id: UUID of the session to delete.

        Returns:
            True if the file was deleted, False if it didn't exist.
        """
        path = self._session_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def exists(self, session_id: str) -> bool:
        """Check if a session exists on disk.

        Args:
            session_id: UUID of the session to check.

        Returns:
            True if the session file exists.
        """
        return self._session_path(session_id).exists()
