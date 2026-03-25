"""RPC protocol — JSONL command/event types and parsing.

Re-exports all public types from ``isotope_agents.rpc.protocol``.

Usage::

    from isotope_agents.rpc import PromptCommand, parse_command
"""

from __future__ import annotations

from .protocol import (
    AbortCommand,
    AgentEndRpcEvent,
    AgentStartRpcEvent,
    CompactCommand,
    ErrorRpcEvent,
    FollowUpCommand,
    GetStateCommand,
    NewSessionCommand,
    PromptCommand,
    RpcCommand,
    RpcEvent,
    SetModelCommand,
    StateRpcEvent,
    SteerCommand,
    TextDeltaRpcEvent,
    ToolCallEndRpcEvent,
    ToolCallStartRpcEvent,
    parse_command,
)

__all__ = [
    # Commands
    "RpcCommand",
    "PromptCommand",
    "SteerCommand",
    "FollowUpCommand",
    "AbortCommand",
    "GetStateCommand",
    "SetModelCommand",
    "CompactCommand",
    "NewSessionCommand",
    # Events
    "RpcEvent",
    "AgentStartRpcEvent",
    "TextDeltaRpcEvent",
    "ToolCallStartRpcEvent",
    "ToolCallEndRpcEvent",
    "AgentEndRpcEvent",
    "StateRpcEvent",
    "ErrorRpcEvent",
    # Parser
    "parse_command",
]
