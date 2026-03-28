"""Tests for the RPC server."""

from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from isotopes.rpc.protocol import (
    AgentEndRpcEvent,
    AgentStartRpcEvent,
    TextDeltaRpcEvent,
)
from isotopes.rpc.server import RpcServer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_agent(**overrides: object) -> MagicMock:
    """Create a mock IsotopeAgent with sensible defaults."""
    agent = MagicMock()
    agent._model = overrides.get("model", "test-model")
    agent.preset = MagicMock()
    agent.preset.name = overrides.get("preset_name", "coding")
    agent.session_id = overrides.get("session_id", "sess-01")
    agent.abort = MagicMock()

    # agent.run returns an async generator that yields nothing by default
    async def _empty_run(*_args: object, **_kwargs: object):  # type: ignore[no-untyped-def]
        return
        yield  # make it an async generator  # noqa: RET504

    agent.run = _empty_run
    agent.steer = AsyncMock()
    agent.follow_up = AsyncMock()
    agent.compact = AsyncMock()
    agent.core = MagicMock()
    agent.core.replace_messages = MagicMock()

    return agent


def _output_lines(output: io.StringIO) -> list[dict[str, object]]:
    """Parse all JSONL lines from a StringIO output stream."""
    output.seek(0)
    lines = []
    for raw in output:
        raw = raw.strip()
        if raw:
            lines.append(json.loads(raw))
    return lines


# ---------------------------------------------------------------------------
# _emit tests
# ---------------------------------------------------------------------------


class TestEmit:
    """Tests for RpcServer._emit."""

    def test_emit_writes_jsonl(self) -> None:
        """_emit writes a single JSONL line to the output stream."""
        output = io.StringIO()
        server = RpcServer(_make_mock_agent(), output_stream=output)

        event = TextDeltaRpcEvent(content="hello")
        server._emit(event)

        lines = _output_lines(output)
        assert len(lines) == 1
        assert lines[0]["type"] == "text_delta"
        assert lines[0]["content"] == "hello"

    def test_emit_flushes(self) -> None:
        """_emit calls flush() on the output stream."""
        output = MagicMock()
        server = RpcServer(_make_mock_agent(), output_stream=output)

        server._emit(AgentStartRpcEvent())
        output.flush.assert_called()

    def test_emit_multiple_events(self) -> None:
        """Multiple _emit calls produce multiple JSONL lines."""
        output = io.StringIO()
        server = RpcServer(_make_mock_agent(), output_stream=output)

        server._emit(AgentStartRpcEvent(stream_id="s1"))
        server._emit(TextDeltaRpcEvent(content="a", stream_id="s1"))
        server._emit(AgentEndRpcEvent(stream_id="s1"))

        lines = _output_lines(output)
        assert len(lines) == 3
        assert [ev["type"] for ev in lines] == [
            "agent_start",
            "text_delta",
            "agent_end",
        ]


# ---------------------------------------------------------------------------
# Prompt command
# ---------------------------------------------------------------------------


class TestPromptCommand:
    """Tests for prompt command dispatch."""

    @pytest.mark.asyncio
    async def test_prompt_streams_agent_events(self) -> None:
        """Prompt command runs agent and maps events to RPC events."""
        from isotopes_core.types import (
            AgentStartEvent,
            AssistantMessage,
            MessageUpdateEvent,
            TextContent,
            ToolEndEvent,
            ToolStartEvent,
            Usage,
        )

        mock_agent = _make_mock_agent()

        # Build a real AssistantMessage for the MessageUpdateEvent
        assistant_msg = AssistantMessage(
            content=[TextContent(text="Hello world")],
            usage=Usage(input_tokens=10, output_tokens=5),
            timestamp=1000,
        )

        # Simulate a sequence of agent events
        async def mock_run(message: str, **kwargs: object):  # type: ignore[no-untyped-def]
            yield AgentStartEvent()
            yield MessageUpdateEvent(
                message=assistant_msg,
                delta="Hello ",
            )
            yield MessageUpdateEvent(
                message=assistant_msg,
                delta="world",
            )
            yield ToolStartEvent(
                tool_call_id="tc-1",
                tool_name="bash",
                args={"cmd": "ls"},
            )
            yield ToolEndEvent(
                tool_call_id="tc-1",
                tool_name="bash",
                result="file.txt",
                is_error=False,
            )

        mock_agent.run = mock_run

        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "prompt", "id": "p1", "content": "Hi"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        types = [ev["type"] for ev in lines]

        assert "agent_start" in types
        assert "text_delta" in types
        assert "tool_call_start" in types
        assert "tool_call_end" in types
        assert "agent_end" in types

        # Check text deltas
        deltas = [ev for ev in lines if ev["type"] == "text_delta"]
        assert deltas[0]["content"] == "Hello "
        assert deltas[1]["content"] == "world"

        # Check tool call events
        tc_start = [ev for ev in lines if ev["type"] == "tool_call_start"][0]
        assert tc_start["name"] == "bash"
        assert tc_start["arguments"] == {"cmd": "ls"}

        tc_end = [ev for ev in lines if ev["type"] == "tool_call_end"][0]
        assert tc_end["name"] == "bash"
        assert tc_end["output"] == "file.txt"
        assert tc_end["is_error"] is False

    @pytest.mark.asyncio
    async def test_prompt_with_no_events(self) -> None:
        """Prompt command emits agent_start and agent_end even with no events."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "prompt", "content": "empty"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        types = [ev["type"] for ev in lines]
        assert types[0] == "agent_start"
        assert types[-1] == "agent_end"


# ---------------------------------------------------------------------------
# Abort command
# ---------------------------------------------------------------------------


class TestAbortCommand:
    """Tests for abort command dispatch."""

    @pytest.mark.asyncio
    async def test_abort_calls_agent_abort(self) -> None:
        """Abort command calls agent.abort()."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "abort"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        mock_agent.abort.assert_called_once()


# ---------------------------------------------------------------------------
# GetState command
# ---------------------------------------------------------------------------


class TestGetStateCommand:
    """Tests for get_state command dispatch."""

    @pytest.mark.asyncio
    async def test_get_state_emits_state_event(self) -> None:
        """get_state command emits StateRpcEvent with agent info."""
        mock_agent = _make_mock_agent(
            model="claude-3-opus",
            preset_name="assistant",
            session_id="sess-42",
        )

        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "get_state", "id": "g1"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        assert len(lines) == 1
        assert lines[0]["type"] == "state"
        assert lines[0]["model"] == "claude-3-opus"
        assert lines[0]["preset"] == "assistant"
        assert lines[0]["session_id"] == "sess-42"
        assert lines[0]["stream_id"] == "g1"


# ---------------------------------------------------------------------------
# Invalid / error commands
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for error handling and invalid commands."""

    @pytest.mark.asyncio
    async def test_invalid_json_emits_error(self) -> None:
        """Invalid JSON emits an ErrorRpcEvent."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        inp = io.StringIO("not valid json\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        assert len(lines) == 1
        assert lines[0]["type"] == "error"
        assert "Invalid JSON" in lines[0]["message"]

    @pytest.mark.asyncio
    async def test_unknown_type_emits_error(self) -> None:
        """Unknown command type emits an ErrorRpcEvent."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "explode"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        assert len(lines) == 1
        assert lines[0]["type"] == "error"
        assert "Unknown command type" in lines[0]["message"]

    @pytest.mark.asyncio
    async def test_missing_type_emits_error(self) -> None:
        """Missing type field emits an ErrorRpcEvent."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"content": "no type field"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        assert len(lines) == 1
        assert lines[0]["type"] == "error"
        assert "Missing 'type' field" in lines[0]["message"]

    @pytest.mark.asyncio
    async def test_error_preserves_command_id(self) -> None:
        """ErrorRpcEvent includes command_id when available."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "explode", "id": "err-1"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        assert lines[0]["command_id"] == "err-1"

    @pytest.mark.asyncio
    async def test_error_preserves_integer_command_id(self) -> None:
        """ErrorRpcEvent preserves integer command_id (P0 fix)."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        # Standard JSON-RPC uses integer id — this used to crash with
        # a Pydantic ValidationError on the command_id field.
        cmd_line = json.dumps({"type": "explode", "id": 42})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        assert lines[0]["type"] == "error"
        assert lines[0]["command_id"] == 42

    @pytest.mark.asyncio
    async def test_prompt_with_integer_id(self) -> None:
        """Prompt command with integer id does not crash (P0 fix)."""
        mock_agent = _make_mock_agent()

        async def mock_run(message: str, **kwargs: object):  # type: ignore[no-untyped-def]
            return
            yield  # make it an async generator  # noqa: RUF027

        mock_agent.run = mock_run

        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "prompt", "id": 7, "content": "Hi"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        types = [ev["type"] for ev in lines]
        assert "agent_start" in types
        assert "agent_end" in types

    @pytest.mark.asyncio
    async def test_handler_exception_emits_error(self) -> None:
        """Exception in a handler emits ErrorRpcEvent."""
        mock_agent = _make_mock_agent()
        mock_agent.compact = AsyncMock(side_effect=RuntimeError("boom"))

        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "compact"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        assert len(lines) == 1
        assert lines[0]["type"] == "error"
        assert "boom" in lines[0]["message"]


# ---------------------------------------------------------------------------
# NewSession command
# ---------------------------------------------------------------------------


class TestNewSessionCommand:
    """Tests for new_session command dispatch."""

    @pytest.mark.asyncio
    async def test_new_session_clears_messages(self) -> None:
        """new_session clears the agent's message history."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "new_session"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        mock_agent.core.replace_messages.assert_called_once_with([])


# ---------------------------------------------------------------------------
# Steer / follow_up commands
# ---------------------------------------------------------------------------


class TestSteerFollowUpCommands:
    """Tests for steer and follow_up command dispatch."""

    @pytest.mark.asyncio
    async def test_steer_calls_agent_steer(self) -> None:
        """Steer command delegates to agent.steer()."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "steer", "content": "Be concise"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        mock_agent.steer.assert_called_once_with("Be concise")

    @pytest.mark.asyncio
    async def test_follow_up_calls_agent_follow_up(self) -> None:
        """Follow-up command delegates to agent.follow_up()."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmd_line = json.dumps({"type": "follow_up", "content": "More info?"})
        inp = io.StringIO(cmd_line + "\n")
        server._input = inp

        await server.run()

        mock_agent.follow_up.assert_called_once_with("More info?")


# ---------------------------------------------------------------------------
# Stop / EOF
# ---------------------------------------------------------------------------


class TestRunLoop:
    """Tests for the run loop lifecycle."""

    @pytest.mark.asyncio
    async def test_eof_stops_loop(self) -> None:
        """Empty input (EOF) causes run() to return."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        server._input = io.StringIO("")  # immediate EOF
        await server.run()
        # If we get here, the loop terminated correctly

    @pytest.mark.asyncio
    async def test_blank_lines_are_skipped(self) -> None:
        """Blank lines in the input are silently skipped."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        inp = io.StringIO("\n\n\n")
        server._input = inp

        await server.run()

        lines = _output_lines(output)
        assert lines == []

    @pytest.mark.asyncio
    async def test_multiple_commands_processed(self) -> None:
        """Multiple commands on successive lines are all processed."""
        mock_agent = _make_mock_agent()
        output = io.StringIO()
        server = RpcServer(mock_agent, output_stream=output)

        cmds = (
            "\n".join(
                [
                    json.dumps({"type": "get_state", "id": "g1"}),
                    json.dumps({"type": "get_state", "id": "g2"}),
                ]
            )
            + "\n"
        )
        server._input = io.StringIO(cmds)

        await server.run()

        lines = _output_lines(output)
        assert len(lines) == 2
        assert all(ev["type"] == "state" for ev in lines)
