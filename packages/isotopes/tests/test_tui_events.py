"""Tests for isotopes.tui.events module.

Tests the pure event-to-display-action mapping extracted from app.py.
Each test constructs an AgentEvent and verifies that process_event()
returns the expected EventAction list.
"""

from __future__ import annotations

from isotopes_core.types import (
    AgentEndEvent,
    AgentStartEvent,
    AssistantMessage,
    ContextPrunedEvent,
    FollowUpEvent,
    LoopDetectedEvent,
    MessageEndEvent,
    MessageUpdateEvent,
    SteerEvent,
    TextContent,
    ToolEndEvent,
    ToolStartEvent,
    TurnEndEvent,
    TurnStartEvent,
    Usage,
    UserMessage,
)

from isotopes.tui.events import EventAction, process_event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = 1_700_000_000_000  # fixed timestamp for tests


def _assistant_message(
    text: str = "hello",
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> AssistantMessage:
    """Build a minimal AssistantMessage for testing."""
    return AssistantMessage(
        content=[TextContent(text=text)],
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        timestamp=_TS,
    )


def _user_message(text: str = "hi") -> UserMessage:
    """Build a minimal UserMessage for testing."""
    return UserMessage(
        content=[TextContent(text=text)],
        timestamp=_TS,
    )


# ---------------------------------------------------------------------------
# MessageUpdateEvent → text action
# ---------------------------------------------------------------------------


class TestMessageUpdate:
    def test_text_delta(self) -> None:
        event = MessageUpdateEvent(
            message=_assistant_message(),
            delta="Hello world",
        )
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "text"
        assert actions[0].content == "Hello world"

    def test_none_delta(self) -> None:
        event = MessageUpdateEvent(
            message=_assistant_message(),
            delta=None,
        )
        actions = process_event(event)
        assert len(actions) == 0

    def test_empty_delta(self) -> None:
        event = MessageUpdateEvent(
            message=_assistant_message(),
            delta="",
        )
        actions = process_event(event)
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# ToolStartEvent → tool_start action
# ---------------------------------------------------------------------------


class TestToolStart:
    def test_basic(self) -> None:
        event = ToolStartEvent(
            tool_call_id="tc_1",
            tool_name="bash",
            args={"command": "ls"},
        )
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "tool_start"
        assert actions[0].tool_name == "bash"
        assert "ls" in actions[0].content

    def test_empty_args(self) -> None:
        event = ToolStartEvent(
            tool_call_id="tc_2",
            tool_name="read",
            args={},
        )
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "tool_start"
        assert actions[0].tool_name == "read"


# ---------------------------------------------------------------------------
# ToolEndEvent → tool_end action (success and error)
# ---------------------------------------------------------------------------


class TestToolEnd:
    def test_success(self) -> None:
        event = ToolEndEvent(
            tool_call_id="tc_1",
            tool_name="bash",
            result="file1.py\nfile2.py",
            is_error=False,
        )
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "tool_end"
        assert actions[0].tool_name == "bash"
        assert "file1.py" in actions[0].content
        assert actions[0].is_error is False

    def test_error(self) -> None:
        event = ToolEndEvent(
            tool_call_id="tc_2",
            tool_name="bash",
            result="command not found",
            is_error=True,
        )
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "tool_end"
        assert actions[0].is_error is True
        assert "command not found" in actions[0].content

    def test_dict_result(self) -> None:
        """Tool results that are dicts get JSON-serialized."""
        event = ToolEndEvent(
            tool_call_id="tc_3",
            tool_name="web_fetch",
            result={"status": 200, "body": "ok"},
        )
        actions = process_event(event)
        assert len(actions) == 1
        assert "200" in actions[0].content
        assert "ok" in actions[0].content

    def test_empty_result(self) -> None:
        event = ToolEndEvent(
            tool_call_id="tc_4",
            tool_name="bash",
            result="",
        )
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "tool_end"
        assert actions[0].content == ""


# ---------------------------------------------------------------------------
# MessageEndEvent → message_end action
# ---------------------------------------------------------------------------


class TestMessageEnd:
    def test_assistant_message_with_text(self) -> None:
        msg = _assistant_message("Here is the answer.")
        event = MessageEndEvent(message=msg)
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "message_end"
        assert actions[0].content == "Here is the answer."

    def test_assistant_message_empty_text(self) -> None:
        """Empty text content blocks produce no message_end action."""
        msg = AssistantMessage(
            content=[TextContent(text="")],
            timestamp=_TS,
        )
        event = MessageEndEvent(message=msg)
        actions = process_event(event)
        # No message_end action because text is empty
        assert len(actions) == 0

    def test_user_message_ignored(self) -> None:
        """Non-assistant messages produce no message_end action."""
        msg = _user_message("hello")
        event = MessageEndEvent(message=msg)
        actions = process_event(event)
        assert len(actions) == 0

    def test_assistant_message_no_text_blocks(self) -> None:
        """Assistant message with no TextContent blocks produces no action."""
        from isotopes_core.types import ToolCallContent

        msg = AssistantMessage(
            content=[ToolCallContent(id="tc_1", name="bash", arguments={"cmd": "ls"})],
            timestamp=_TS,
        )
        event = MessageEndEvent(message=msg)
        actions = process_event(event)
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# TurnEndEvent → usage action with token counts
# ---------------------------------------------------------------------------


class TestTurnEnd:
    def test_usage_action(self) -> None:
        msg = _assistant_message(input_tokens=150, output_tokens=75)
        event = TurnEndEvent(message=msg)
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "usage"
        assert actions[0].input_tokens == 150
        assert actions[0].output_tokens == 75

    def test_zero_tokens(self) -> None:
        msg = _assistant_message(input_tokens=0, output_tokens=0)
        event = TurnEndEvent(message=msg)
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "usage"
        assert actions[0].input_tokens == 0
        assert actions[0].output_tokens == 0

    def test_user_message_ignored(self) -> None:
        """TurnEnd with a non-assistant message produces no usage action."""
        msg = _user_message()
        event = TurnEndEvent(message=msg)
        actions = process_event(event)
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# AgentEndEvent
# ---------------------------------------------------------------------------


class TestAgentEnd:
    def test_completed_no_debug(self) -> None:
        """A completed agent_end with debug=False produces no actions."""
        event = AgentEndEvent(reason="completed")
        actions = process_event(event, debug=False)
        assert len(actions) == 0

    def test_completed_debug(self) -> None:
        """A completed agent_end in debug mode only produces the type label."""
        event = AgentEndEvent(reason="completed")
        actions = process_event(event, debug=True)
        # Only the generic debug label, no extra "ended:" debug action
        assert len(actions) == 1
        assert actions[0].content == "[agent_end]"

    def test_non_completed_debug(self) -> None:
        """Non-completed reason in debug mode produces the ended: action."""
        event = AgentEndEvent(reason="budget_exceeded")
        actions = process_event(event, debug=True)
        assert len(actions) == 2
        assert actions[0].content == "[agent_end]"
        assert "budget_exceeded" in actions[1].content

    def test_non_completed_no_debug(self) -> None:
        """Non-completed reason without debug produces no actions."""
        event = AgentEndEvent(reason="budget_exceeded")
        actions = process_event(event, debug=False)
        assert len(actions) == 0


# ---------------------------------------------------------------------------
# SteerEvent
# ---------------------------------------------------------------------------


class TestSteer:
    def test_steer_no_debug(self) -> None:
        msg = _user_message("redirect")
        event = SteerEvent(message=msg, turn_number=3)
        actions = process_event(event, debug=False)
        assert len(actions) == 0

    def test_steer_debug(self) -> None:
        msg = _user_message("redirect")
        event = SteerEvent(message=msg, turn_number=3)
        actions = process_event(event, debug=True)
        assert len(actions) == 2
        assert actions[0].content == "[steer]"
        assert "steer applied" in actions[1].content
        assert "3" in actions[1].content


# ---------------------------------------------------------------------------
# FollowUpEvent
# ---------------------------------------------------------------------------


class TestFollowUp:
    def test_follow_up_no_debug(self) -> None:
        msg = _user_message("continue")
        event = FollowUpEvent(message=msg, turn_number=5)
        actions = process_event(event, debug=False)
        assert len(actions) == 0

    def test_follow_up_debug(self) -> None:
        msg = _user_message("continue")
        event = FollowUpEvent(message=msg, turn_number=5)
        actions = process_event(event, debug=True)
        assert len(actions) == 2
        assert actions[0].content == "[follow_up]"
        assert "follow-up applied" in actions[1].content
        assert "5" in actions[1].content


# ---------------------------------------------------------------------------
# LoopDetectedEvent
# ---------------------------------------------------------------------------


class TestLoopDetected:
    def test_loop_detected_no_debug(self) -> None:
        event = LoopDetectedEvent(
            tool_name="bash",
            count=5,
            message="Loop detected",
        )
        actions = process_event(event, debug=False)
        assert len(actions) == 0

    def test_loop_detected_debug(self) -> None:
        event = LoopDetectedEvent(
            tool_name="bash",
            count=5,
            message="Loop detected",
        )
        actions = process_event(event, debug=True)
        assert len(actions) == 2
        assert "loop detected" in actions[1].content.lower()
        assert "bash" in actions[1].content
        assert "5" in actions[1].content


# ---------------------------------------------------------------------------
# Debug mode: unknown events produce debug actions
# ---------------------------------------------------------------------------


class TestDebugMode:
    def test_unknown_event_debug_on(self) -> None:
        """Unknown/unhandled events produce debug actions when debug=True."""
        event = AgentStartEvent()
        actions = process_event(event, debug=True)
        # Generic label + repr fallback for unhandled branch
        assert len(actions) >= 2
        assert actions[0].type == "debug"
        assert actions[0].content == "[agent_start]"
        # The fallback debug action has repr of the event
        assert actions[1].type == "debug"

    def test_unknown_event_debug_off(self) -> None:
        """Unknown/unhandled events produce 'none' when debug=False."""
        event = AgentStartEvent()
        actions = process_event(event, debug=False)
        assert len(actions) == 1
        assert actions[0].type == "none"

    def test_debug_label_for_every_event(self) -> None:
        """In debug mode, every event gets a leading type label."""
        event = MessageUpdateEvent(
            message=_assistant_message(),
            delta="hi",
        )
        actions = process_event(event, debug=True)
        assert actions[0].type == "debug"
        assert "[message_update]" in actions[0].content
        # The actual text action follows
        assert actions[1].type == "text"

    def test_context_pruned_no_debug(self) -> None:
        """ContextPrunedEvent is unknown to the display — produces none."""
        event = ContextPrunedEvent(
            strategy="sliding_window",
            pruned_count=3,
            pruned_tokens=1500,
            remaining_tokens=5000,
        )
        actions = process_event(event, debug=False)
        assert len(actions) == 1
        assert actions[0].type == "none"

    def test_turn_start_debug_off(self) -> None:
        """TurnStartEvent is not explicitly handled — produces none."""
        event = TurnStartEvent()
        actions = process_event(event, debug=False)
        assert len(actions) == 1
        assert actions[0].type == "none"


# ---------------------------------------------------------------------------
# EventAction dataclass defaults
# ---------------------------------------------------------------------------


class TestEventAction:
    def test_defaults(self) -> None:
        action = EventAction(type="text")
        assert action.content == ""
        assert action.tool_name == ""
        assert action.is_error is False
        assert action.input_tokens == 0
        assert action.output_tokens == 0

    def test_custom_values(self) -> None:
        action = EventAction(
            type="tool_end",
            content="output",
            tool_name="bash",
            is_error=True,
            input_tokens=10,
            output_tokens=20,
        )
        assert action.type == "tool_end"
        assert action.content == "output"
        assert action.tool_name == "bash"
        assert action.is_error is True
        assert action.input_tokens == 10
        assert action.output_tokens == 20


# ---------------------------------------------------------------------------
# Edge cases: events with missing/optional fields
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_message_update_default_delta(self) -> None:
        """MessageUpdateEvent with default (None) delta."""
        event = MessageUpdateEvent(message=_assistant_message())
        actions = process_event(event)
        assert len(actions) == 0

    def test_tool_end_none_result(self) -> None:
        """ToolEndEvent with None result."""
        event = ToolEndEvent(
            tool_call_id="tc_1",
            tool_name="bash",
            result=None,
        )
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].type == "tool_end"
        assert actions[0].content == "null"

    def test_agent_end_default_reason(self) -> None:
        """AgentEndEvent uses default reason='completed'."""
        event = AgentEndEvent()
        actions = process_event(event, debug=False)
        # completed + debug=False → no actions
        assert len(actions) == 0

    def test_message_end_multiple_text_blocks(self) -> None:
        """Multiple TextContent blocks are concatenated."""
        msg = AssistantMessage(
            content=[TextContent(text="Hello "), TextContent(text="world!")],
            timestamp=_TS,
        )
        event = MessageEndEvent(message=msg)
        actions = process_event(event)
        assert len(actions) == 1
        assert actions[0].content == "Hello world!"

    def test_tool_start_complex_args(self) -> None:
        """Tool args with nested structures are JSON-formatted."""
        event = ToolStartEvent(
            tool_call_id="tc_1",
            tool_name="edit",
            args={"path": "/tmp/a.py", "changes": [{"line": 1, "text": "x"}]},
        )
        actions = process_event(event)
        assert len(actions) == 1
        assert "/tmp/a.py" in actions[0].content
