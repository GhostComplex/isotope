"""Pure event-to-display-action mapping for the TUI.

This module extracts the event processing logic from app.py into a pure
function that converts AgentEvent instances into EventAction descriptors,
without performing any I/O.  This makes the mapping easy to test and
keeps the rendering layer separate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from isotope_core.types import (
    AgentEndEvent,
    AgentEvent,
    AssistantMessage,
    FollowUpEvent,
    LoopDetectedEvent,
    MessageEndEvent,
    MessageUpdateEvent,
    SteerEvent,
    TextContent,
    ToolEndEvent,
    ToolStartEvent,
    TurnEndEvent,
)


@dataclass
class EventAction:
    """Action to take for a TUI event.

    Each instance describes *what* should be displayed without actually
    touching the terminal.  The caller applies the action to the real UI.
    """

    type: str
    """One of:
    - ``"text"``          – stream text delta
    - ``"tool_start"``    – tool invocation started
    - ``"tool_end"``      – tool invocation finished
    - ``"message_end"``   – full assistant message ready for markdown render
    - ``"usage"``         – token usage from a completed turn
    - ``"debug"``         – debug-only info (event label / repr)
    - ``"none"``          – no display action
    """

    content: str = ""
    tool_name: str = ""
    is_error: bool = False
    input_tokens: int = 0
    output_tokens: int = 0


def _format_tool_args(args: dict[str, object]) -> str:
    """Format tool arguments for display."""
    try:
        return json.dumps(args, indent=2, default=str)
    except (TypeError, ValueError):
        return repr(args)


def _format_tool_result(result: object) -> str:
    """Format a tool result for display."""
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, indent=2, default=str)
    except (TypeError, ValueError):
        return str(result)


def _extract_text(message: AssistantMessage) -> str:
    """Extract concatenated text from an AssistantMessage's content blocks."""
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, TextContent):
            parts.append(block.text)
    return "".join(parts)


def process_event(event: AgentEvent, *, debug: bool = False) -> list[EventAction]:
    """Convert an AgentEvent into display actions, without doing I/O.

    Maps each event type to one or more :class:`EventAction` instances that
    describe what to display, without actually touching the terminal.

    Parameters
    ----------
    event:
        The agent event to process.
    debug:
        When ``True``, emit extra ``"debug"`` actions for every event
        (the event type label) and for events that would otherwise be
        ignored.

    Returns
    -------
    list[EventAction]
        One or more actions.  The caller should apply them in order.
    """
    actions: list[EventAction] = []

    # In debug mode, every event gets a label action first.
    if debug:
        actions.append(EventAction(type="debug", content=f"[{event.type}]"))

    # -- message_update --------------------------------------------------------
    if isinstance(event, MessageUpdateEvent):
        delta = event.delta
        if delta:
            actions.append(EventAction(type="text", content=delta))

    # -- tool_start ------------------------------------------------------------
    elif isinstance(event, ToolStartEvent):
        actions.append(
            EventAction(
                type="tool_start",
                tool_name=event.tool_name,
                content=_format_tool_args(event.args),
            )
        )

    # -- tool_end --------------------------------------------------------------
    elif isinstance(event, ToolEndEvent):
        actions.append(
            EventAction(
                type="tool_end",
                tool_name=event.tool_name,
                content=_format_tool_result(event.result),
                is_error=event.is_error,
            )
        )

    # -- message_end -----------------------------------------------------------
    elif isinstance(event, MessageEndEvent):
        message = event.message
        if isinstance(message, AssistantMessage):
            text = _extract_text(message)
            if text:
                actions.append(EventAction(type="message_end", content=text))

    # -- turn_end (usage) ------------------------------------------------------
    elif isinstance(event, TurnEndEvent):
        message = event.message
        if isinstance(message, AssistantMessage):
            actions.append(
                EventAction(
                    type="usage",
                    input_tokens=message.usage.input_tokens,
                    output_tokens=message.usage.output_tokens,
                )
            )

    # -- steer -----------------------------------------------------------------
    elif isinstance(event, SteerEvent):
        if debug:
            actions.append(
                EventAction(
                    type="debug",
                    content=f"[steer applied, turn {event.turn_number}]",
                )
            )

    # -- follow_up -------------------------------------------------------------
    elif isinstance(event, FollowUpEvent):
        if debug:
            actions.append(
                EventAction(
                    type="debug",
                    content=f"[follow-up applied, turn {event.turn_number}]",
                )
            )

    # -- agent_end -------------------------------------------------------------
    elif isinstance(event, AgentEndEvent):
        if event.reason != "completed" and debug:
            actions.append(
                EventAction(type="debug", content=f"[ended: {event.reason}]")
            )

    # -- loop_detected ---------------------------------------------------------
    elif isinstance(event, LoopDetectedEvent):
        if debug:
            actions.append(
                EventAction(
                    type="debug",
                    content=f"[loop detected: {event.tool_name} x{event.count}]",
                )
            )

    # -- unknown / unhandled events -------------------------------------------
    else:
        if debug:
            actions.append(
                EventAction(type="debug", content=repr(event))
            )
        else:
            actions.append(EventAction(type="none"))

    return actions
