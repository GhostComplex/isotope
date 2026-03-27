"""Tests for RPC protocol types and parse_command."""

from __future__ import annotations

import json

import pytest

from isotope_agents.rpc.protocol import (
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


# =============================================================================
# Command serialization / deserialization
# =============================================================================


class TestCommandTypes:
    """Tests for each RpcCommand subclass."""

    def test_prompt_command_defaults(self) -> None:
        """PromptCommand has correct type and default images list."""
        cmd = PromptCommand(content="Hello")
        assert cmd.type == "prompt"
        assert cmd.content == "Hello"
        assert cmd.images == []
        assert cmd.id is None

    def test_prompt_command_with_images(self) -> None:
        """PromptCommand accepts images and an id."""
        cmd = PromptCommand(id="p1", content="Describe", images=["b64data"])
        assert cmd.id == "p1"
        assert cmd.images == ["b64data"]

    def test_prompt_command_roundtrip(self) -> None:
        """PromptCommand survives JSON roundtrip."""
        cmd = PromptCommand(id="r1", content="test", images=["a", "b"])
        data = json.loads(cmd.model_dump_json())
        restored = PromptCommand.model_validate(data)
        assert restored == cmd

    def test_steer_command(self) -> None:
        """SteerCommand serialization."""
        cmd = SteerCommand(content="Be concise")
        assert cmd.type == "steer"
        assert cmd.content == "Be concise"
        data = cmd.model_dump()
        assert data["type"] == "steer"

    def test_follow_up_command(self) -> None:
        """FollowUpCommand serialization."""
        cmd = FollowUpCommand(content="What about X?")
        assert cmd.type == "follow_up"
        assert cmd.content == "What about X?"

    def test_abort_command(self) -> None:
        """AbortCommand has no extra fields."""
        cmd = AbortCommand()
        assert cmd.type == "abort"
        assert cmd.id is None

    def test_get_state_command(self) -> None:
        """GetStateCommand serialization."""
        cmd = GetStateCommand(id="s1")
        assert cmd.type == "get_state"
        assert cmd.id == "s1"

    def test_set_model_command(self) -> None:
        """SetModelCommand carries model name."""
        cmd = SetModelCommand(model="claude-3-opus")
        assert cmd.type == "set_model"
        assert cmd.model == "claude-3-opus"

    def test_compact_command(self) -> None:
        """CompactCommand serialization."""
        cmd = CompactCommand()
        assert cmd.type == "compact"

    def test_new_session_command(self) -> None:
        """NewSessionCommand serialization."""
        cmd = NewSessionCommand()
        assert cmd.type == "new_session"

    def test_all_commands_inherit_rpc_command(self) -> None:
        """Every command subclass is an RpcCommand."""
        classes = [
            PromptCommand,
            SteerCommand,
            FollowUpCommand,
            AbortCommand,
            GetStateCommand,
            SetModelCommand,
            CompactCommand,
            NewSessionCommand,
        ]
        for cls in classes:
            assert issubclass(cls, RpcCommand)


# =============================================================================
# Event serialization
# =============================================================================


class TestEventTypes:
    """Tests for each RpcEvent subclass."""

    def test_agent_start_event(self) -> None:
        """AgentStartRpcEvent has correct type."""
        evt = AgentStartRpcEvent()
        assert evt.type == "agent_start"
        assert evt.stream_id is None

    def test_agent_start_event_with_stream_id(self) -> None:
        """AgentStartRpcEvent accepts a stream_id."""
        evt = AgentStartRpcEvent(stream_id="s-123")
        assert evt.stream_id == "s-123"

    def test_text_delta_event(self) -> None:
        """TextDeltaRpcEvent carries content."""
        evt = TextDeltaRpcEvent(content="Hello ")
        assert evt.type == "text_delta"
        assert evt.content == "Hello "

    def test_tool_call_start_event(self) -> None:
        """ToolCallStartRpcEvent carries name and arguments."""
        evt = ToolCallStartRpcEvent(name="bash", arguments={"cmd": "ls"})
        assert evt.type == "tool_call_start"
        assert evt.name == "bash"
        assert evt.arguments == {"cmd": "ls"}

    def test_tool_call_start_event_default_args(self) -> None:
        """ToolCallStartRpcEvent defaults arguments to empty dict."""
        evt = ToolCallStartRpcEvent(name="get_state")
        assert evt.arguments == {}

    def test_tool_call_end_event(self) -> None:
        """ToolCallEndRpcEvent carries name, output, and is_error."""
        evt = ToolCallEndRpcEvent(name="bash", output="file.txt", is_error=False)
        assert evt.type == "tool_call_end"
        assert evt.name == "bash"
        assert evt.output == "file.txt"
        assert evt.is_error is False

    def test_tool_call_end_event_error(self) -> None:
        """ToolCallEndRpcEvent with error flag."""
        evt = ToolCallEndRpcEvent(name="bash", output="not found", is_error=True)
        assert evt.is_error is True

    def test_agent_end_event(self) -> None:
        """AgentEndRpcEvent carries usage dict."""
        usage = {"input_tokens": 100, "output_tokens": 50}
        evt = AgentEndRpcEvent(usage=usage)
        assert evt.type == "agent_end"
        assert evt.usage == usage

    def test_agent_end_event_default_usage(self) -> None:
        """AgentEndRpcEvent defaults usage to empty dict."""
        evt = AgentEndRpcEvent()
        assert evt.usage == {}

    def test_state_event(self) -> None:
        """StateRpcEvent carries model, preset, session_id."""
        evt = StateRpcEvent(model="gpt-4", preset="coding", session_id="sess-1")
        assert evt.type == "state"
        assert evt.model == "gpt-4"
        assert evt.preset == "coding"
        assert evt.session_id == "sess-1"

    def test_error_event(self) -> None:
        """ErrorRpcEvent carries message and optional command_id."""
        evt = ErrorRpcEvent(message="Something broke")
        assert evt.type == "error"
        assert evt.message == "Something broke"
        assert evt.command_id is None

    def test_error_event_with_command_id(self) -> None:
        """ErrorRpcEvent with command_id."""
        evt = ErrorRpcEvent(message="Bad input", command_id="cmd-42")
        assert evt.command_id == "cmd-42"

    def test_all_events_inherit_rpc_event(self) -> None:
        """Every event subclass is an RpcEvent."""
        classes = [
            AgentStartRpcEvent,
            TextDeltaRpcEvent,
            ToolCallStartRpcEvent,
            ToolCallEndRpcEvent,
            AgentEndRpcEvent,
            StateRpcEvent,
            ErrorRpcEvent,
        ]
        for cls in classes:
            assert issubclass(cls, RpcEvent)

    def test_event_json_roundtrip(self) -> None:
        """Events survive a JSON roundtrip."""
        evt = TextDeltaRpcEvent(content="chunk", stream_id="s1")
        data = json.loads(evt.model_dump_json())
        restored = TextDeltaRpcEvent.model_validate(data)
        assert restored == evt


# =============================================================================
# parse_command
# =============================================================================


class TestParseCommand:
    """Tests for the parse_command helper."""

    @pytest.mark.parametrize(
        ("json_str", "expected_type", "check"),
        [
            (
                '{"type": "prompt", "content": "Hi"}',
                PromptCommand,
                lambda c: c.content == "Hi",
            ),
            (
                '{"type": "steer", "content": "Be brief"}',
                SteerCommand,
                lambda c: c.content == "Be brief",
            ),
            (
                '{"type": "follow_up", "content": "More?"}',
                FollowUpCommand,
                lambda c: c.content == "More?",
            ),
            (
                '{"type": "abort"}',
                AbortCommand,
                lambda c: c.type == "abort",
            ),
            (
                '{"type": "get_state", "id": "g1"}',
                GetStateCommand,
                lambda c: c.id == "g1",
            ),
            (
                '{"type": "set_model", "model": "opus"}',
                SetModelCommand,
                lambda c: c.model == "opus",
            ),
            (
                '{"type": "compact"}',
                CompactCommand,
                lambda c: c.type == "compact",
            ),
            (
                '{"type": "new_session"}',
                NewSessionCommand,
                lambda c: c.type == "new_session",
            ),
        ],
    )
    def test_parse_valid_commands(
        self, json_str: str, expected_type: type, check: object
    ) -> None:
        """parse_command returns the correct subclass for each type."""
        cmd = parse_command(json_str)
        assert isinstance(cmd, expected_type)
        assert check(cmd)  # type: ignore[operator]

    def test_parse_command_preserves_id(self) -> None:
        """parse_command preserves the optional id field."""
        cmd = parse_command('{"type": "abort", "id": "x99"}')
        assert cmd.id == "x99"

    def test_parse_command_unknown_type(self) -> None:
        """parse_command raises ValueError for an unknown type."""
        with pytest.raises(ValueError, match="Unknown command type"):
            parse_command('{"type": "explode"}')

    def test_parse_command_missing_type(self) -> None:
        """parse_command raises ValueError when type field is missing."""
        with pytest.raises(ValueError, match="Missing 'type' field"):
            parse_command('{"content": "no type"}')

    def test_parse_command_invalid_json(self) -> None:
        """parse_command raises ValueError for malformed JSON."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_command("not json at all")

    def test_parse_command_non_object_json(self) -> None:
        """parse_command raises ValueError for JSON arrays, strings, etc."""
        with pytest.raises(ValueError, match="Expected JSON object"):
            parse_command("[1, 2, 3]")

    def test_parse_command_prompt_with_images(self) -> None:
        """parse_command correctly deserialises a prompt with images."""
        line = json.dumps(
            {
                "type": "prompt",
                "id": "img-1",
                "content": "Describe this",
                "images": ["base64data1", "base64data2"],
            }
        )
        cmd = parse_command(line)
        assert isinstance(cmd, PromptCommand)
        assert cmd.images == ["base64data1", "base64data2"]

    def test_parse_command_integer_id(self) -> None:
        """parse_command accepts integer id (standard JSON-RPC convention)."""
        cmd = parse_command('{"type": "prompt", "id": 42, "content": "Hi"}')
        assert isinstance(cmd, PromptCommand)
        assert cmd.id == 42
        assert cmd.content == "Hi"

    def test_parse_command_integer_id_on_abort(self) -> None:
        """parse_command accepts integer id on commands without content."""
        cmd = parse_command('{"type": "abort", "id": 1}')
        assert isinstance(cmd, AbortCommand)
        assert cmd.id == 1


class TestIntegerIdSupport:
    """Tests for integer id support in commands and events (P0 fix)."""

    def test_command_with_integer_id(self) -> None:
        """RpcCommand accepts integer id."""
        cmd = PromptCommand(id=42, content="Hello")
        assert cmd.id == 42

    def test_command_with_string_id(self) -> None:
        """RpcCommand still accepts string id."""
        cmd = PromptCommand(id="abc", content="Hello")
        assert cmd.id == "abc"

    def test_command_with_none_id(self) -> None:
        """RpcCommand still accepts None id."""
        cmd = PromptCommand(content="Hello")
        assert cmd.id is None

    def test_error_event_with_integer_command_id(self) -> None:
        """ErrorRpcEvent accepts integer command_id."""
        evt = ErrorRpcEvent(message="fail", command_id=42)
        assert evt.command_id == 42

    def test_error_event_integer_roundtrip(self) -> None:
        """ErrorRpcEvent with integer command_id survives JSON roundtrip."""
        evt = ErrorRpcEvent(message="fail", command_id=99)
        data = json.loads(evt.model_dump_json())
        restored = ErrorRpcEvent.model_validate(data)
        assert restored.command_id == 99
