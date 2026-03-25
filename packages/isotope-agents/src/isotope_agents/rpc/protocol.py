"""RPC protocol types for the JSONL-based agent communication protocol.

Defines Pydantic models for commands (stdin → agent) and events (agent → stdout),
plus a ``parse_command`` helper that deserialises a single JSONL line into the
appropriate command subclass.
"""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel

# =============================================================================
# Commands (stdin → agent)
# =============================================================================


class RpcCommand(BaseModel):
    """Base class for all RPC commands sent to the agent."""

    id: str | None = None
    type: str


class PromptCommand(RpcCommand):
    """Send a new user prompt to the agent."""

    type: Literal["prompt"] = "prompt"
    content: str
    images: list[str] = []


class SteerCommand(RpcCommand):
    """Inject a steering instruction into the current turn."""

    type: Literal["steer"] = "steer"
    content: str


class FollowUpCommand(RpcCommand):
    """Queue a follow-up message for the next turn."""

    type: Literal["follow_up"] = "follow_up"
    content: str


class AbortCommand(RpcCommand):
    """Abort the currently running agent turn."""

    type: Literal["abort"] = "abort"


class GetStateCommand(RpcCommand):
    """Request the current agent state snapshot."""

    type: Literal["get_state"] = "get_state"


class SetModelCommand(RpcCommand):
    """Change the model used by the agent."""

    type: Literal["set_model"] = "set_model"
    model: str


class CompactCommand(RpcCommand):
    """Trigger context compaction."""

    type: Literal["compact"] = "compact"


class NewSessionCommand(RpcCommand):
    """Start a new session, clearing all context."""

    type: Literal["new_session"] = "new_session"


# Lookup table: type string → command class
_COMMAND_TYPES: dict[str, type[RpcCommand]] = {
    "prompt": PromptCommand,
    "steer": SteerCommand,
    "follow_up": FollowUpCommand,
    "abort": AbortCommand,
    "get_state": GetStateCommand,
    "set_model": SetModelCommand,
    "compact": CompactCommand,
    "new_session": NewSessionCommand,
}

# =============================================================================
# Events (agent → stdout)
# =============================================================================


class RpcEvent(BaseModel):
    """Base class for all RPC events emitted by the agent."""

    type: str
    stream_id: str | None = None


class AgentStartRpcEvent(RpcEvent):
    """Emitted when the agent begins processing a prompt."""

    type: Literal["agent_start"] = "agent_start"


class TextDeltaRpcEvent(RpcEvent):
    """Emitted for each chunk of streamed text output."""

    type: Literal["text_delta"] = "text_delta"
    content: str


class ToolCallStartRpcEvent(RpcEvent):
    """Emitted when the agent initiates a tool call."""

    type: Literal["tool_call_start"] = "tool_call_start"
    name: str
    arguments: dict[str, object] = {}


class ToolCallEndRpcEvent(RpcEvent):
    """Emitted when a tool call completes."""

    type: Literal["tool_call_end"] = "tool_call_end"
    name: str
    output: str
    is_error: bool


class AgentEndRpcEvent(RpcEvent):
    """Emitted when the agent finishes processing a prompt."""

    type: Literal["agent_end"] = "agent_end"
    usage: dict[str, object] = {}


class StateRpcEvent(RpcEvent):
    """Emitted in response to a ``get_state`` command."""

    type: Literal["state"] = "state"
    model: str
    preset: str
    session_id: str


class ErrorRpcEvent(RpcEvent):
    """Emitted when an error occurs."""

    type: Literal["error"] = "error"
    message: str
    command_id: str | None = None


# =============================================================================
# Command parser
# =============================================================================


def parse_command(line: str) -> RpcCommand:
    """Parse a JSONL line into the appropriate RpcCommand subclass.

    Args:
        line: A single line of JSON text.

    Returns:
        An instance of the matching RpcCommand subclass.

    Raises:
        ValueError: If the JSON is malformed or the ``type`` field is missing
            or unrecognised.
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    cmd_type = data.get("type")
    if cmd_type is None:
        raise ValueError("Missing 'type' field in command")

    cls = _COMMAND_TYPES.get(cmd_type)
    if cls is None:
        raise ValueError(f"Unknown command type: {cmd_type!r}")

    return cls.model_validate(data)
