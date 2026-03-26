"""Tests for isotope_agents.tui.commands module.

Tests the CommandHandler, CommandResult, and TUIState classes that were
extracted from app.py to be I/O-independent and easily testable.
"""

from __future__ import annotations

import pytest

from isotope_agents.tui.commands import (
    BETWEEN_MESSAGE_COMMANDS,
    DURING_STREAMING_COMMANDS,
    CommandHandler,
    CommandResult,
    TUIState,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakePreset:
    """Minimal stand-in for a Preset with named tools."""

    def __init__(self, tool_names: list[str] | None = None) -> None:
        self.name = "fake"
        self.tools = [_FakeTool(n) for n in (tool_names or [])]


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


def _make_handler(
    *,
    model: str = "test-model",
    tools_enabled: bool = True,
    debug: bool = False,
    preset: _FakePreset | None = None,
    custom_system_prompt: str | None = None,
) -> tuple[CommandHandler, TUIState]:
    """Create a CommandHandler + TUIState pair for testing."""
    state = TUIState(
        model=model,
        preset=preset or _FakePreset(["bash", "read"]),
        tools_enabled=tools_enabled,
        debug=debug,
        custom_system_prompt=custom_system_prompt,
    )
    return CommandHandler(state), state


# ---------------------------------------------------------------------------
# CommandResult defaults
# ---------------------------------------------------------------------------


class TestCommandResult:
    """Test CommandResult dataclass defaults."""

    def test_defaults(self) -> None:
        r = CommandResult()
        assert r.should_quit is False
        assert r.message == ""
        assert r.style == "info"
        assert r.action is None

    def test_custom_values(self) -> None:
        r = CommandResult(should_quit=True, message="bye", style="error", action="quit")
        assert r.should_quit is True
        assert r.message == "bye"
        assert r.style == "error"
        assert r.action == "quit"


# ---------------------------------------------------------------------------
# TUIState defaults
# ---------------------------------------------------------------------------


class TestTUIState:
    """Test TUIState dataclass defaults."""

    def test_defaults(self) -> None:
        state = TUIState()
        assert state.model == ""
        assert state.preset is None
        assert state.tools_enabled is True
        assert state.debug is False
        assert state.custom_system_prompt is None
        assert state.total_input_tokens == 0
        assert state.total_output_tokens == 0

    def test_custom_values(self) -> None:
        state = TUIState(model="gpt-4", debug=True, total_input_tokens=100)
        assert state.model == "gpt-4"
        assert state.debug is True
        assert state.total_input_tokens == 100


# ---------------------------------------------------------------------------
# /quit
# ---------------------------------------------------------------------------


class TestQuit:
    @pytest.mark.asyncio
    async def test_quit(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/quit")
        assert result.should_quit is True
        assert "Bye" in result.message

    @pytest.mark.asyncio
    async def test_quit_uppercase(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/QUIT")
        assert result.should_quit is True


# ---------------------------------------------------------------------------
# /tools
# ---------------------------------------------------------------------------


class TestTools:
    @pytest.mark.asyncio
    async def test_toggle_off(self) -> None:
        handler, state = _make_handler(tools_enabled=True)
        result = await handler.handle("/tools")
        assert state.tools_enabled is False
        assert "disabled" in result.message.lower()
        assert result.action == "rebuild_agent"
        assert result.should_quit is False

    @pytest.mark.asyncio
    async def test_toggle_on(self) -> None:
        handler, state = _make_handler(tools_enabled=False, preset=_FakePreset(["bash"]))
        result = await handler.handle("/tools")
        assert state.tools_enabled is True
        assert "enabled" in result.message.lower()
        assert "bash" in result.message
        assert result.action == "rebuild_agent"

    @pytest.mark.asyncio
    async def test_toggle_on_no_preset(self) -> None:
        """Tools enabled message works even when preset has no tools attr."""
        state = TUIState(tools_enabled=False, preset=None)
        handler = CommandHandler(state)
        result = await handler.handle("/tools")
        assert state.tools_enabled is True
        assert "enabled" in result.message.lower()

    @pytest.mark.asyncio
    async def test_double_toggle(self) -> None:
        handler, state = _make_handler(tools_enabled=True)
        await handler.handle("/tools")
        assert state.tools_enabled is False
        await handler.handle("/tools")
        assert state.tools_enabled is True


# ---------------------------------------------------------------------------
# /model
# ---------------------------------------------------------------------------


class TestModel:
    @pytest.mark.asyncio
    async def test_switch_model(self) -> None:
        handler, state = _make_handler(model="old-model")
        result = await handler.handle("/model new-model")
        assert state.model == "new-model"
        assert "new-model" in result.message
        assert result.action == "rebuild_agent"
        assert result.should_quit is False

    @pytest.mark.asyncio
    async def test_no_arg(self) -> None:
        handler, state = _make_handler(model="old-model")
        result = await handler.handle("/model")
        assert state.model == "old-model"  # unchanged
        assert "Usage" in result.message
        assert result.style == "warn"
        assert result.action is None

    @pytest.mark.asyncio
    async def test_model_with_extra_spaces(self) -> None:
        handler, state = _make_handler()
        result = await handler.handle("/model    gpt-4o  ")
        assert state.model == "gpt-4o"
        assert result.action == "rebuild_agent"

    @pytest.mark.asyncio
    async def test_model_preserves_case(self) -> None:
        handler, state = _make_handler()
        await handler.handle("/model Claude-Opus-4.6")
        assert state.model == "Claude-Opus-4.6"


# ---------------------------------------------------------------------------
# /system
# ---------------------------------------------------------------------------


class TestSystem:
    @pytest.mark.asyncio
    async def test_set_system_prompt(self) -> None:
        handler, state = _make_handler()
        result = await handler.handle("/system Be concise.")
        assert state.custom_system_prompt == "Be concise."
        assert "updated" in result.message.lower()
        assert result.action == "rebuild_agent"
        assert result.should_quit is False

    @pytest.mark.asyncio
    async def test_clear_system_prompt(self) -> None:
        handler, state = _make_handler(custom_system_prompt="old prompt")
        result = await handler.handle("/system clear")
        assert state.custom_system_prompt is None
        assert "cleared" in result.message.lower()
        assert result.action == "rebuild_agent"

    @pytest.mark.asyncio
    async def test_no_arg(self) -> None:
        handler, state = _make_handler()
        result = await handler.handle("/system")
        assert "Usage" in result.message
        assert result.style == "warn"
        assert result.action is None

    @pytest.mark.asyncio
    async def test_system_with_multiword(self) -> None:
        handler, state = _make_handler()
        result = await handler.handle("/system You are a helpful assistant.")
        assert state.custom_system_prompt == "You are a helpful assistant."
        assert result.action == "rebuild_agent"


# ---------------------------------------------------------------------------
# /clear
# ---------------------------------------------------------------------------


class TestClear:
    @pytest.mark.asyncio
    async def test_clear_resets_tokens(self) -> None:
        handler, state = _make_handler()
        state.total_input_tokens = 500
        state.total_output_tokens = 200
        result = await handler.handle("/clear")
        assert state.total_input_tokens == 0
        assert state.total_output_tokens == 0
        assert result.action == "rebuild_agent_clear"
        assert result.should_quit is False

    @pytest.mark.asyncio
    async def test_clear_message(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/clear")
        assert "cleared" in result.message.lower()


# ---------------------------------------------------------------------------
# /compact
# ---------------------------------------------------------------------------


class TestCompact:
    @pytest.mark.asyncio
    async def test_compact_returns_action(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/compact")
        assert result.action == "compact"
        assert result.should_quit is False


# ---------------------------------------------------------------------------
# /history
# ---------------------------------------------------------------------------


class TestHistory:
    @pytest.mark.asyncio
    async def test_history_shows_tokens(self) -> None:
        handler, state = _make_handler()
        state.total_input_tokens = 123
        state.total_output_tokens = 456
        result = await handler.handle("/history")
        assert "123" in result.message
        assert "456" in result.message
        assert result.action == "history"
        assert result.should_quit is False


# ---------------------------------------------------------------------------
# /sessions
# ---------------------------------------------------------------------------


class TestSessions:
    @pytest.mark.asyncio
    async def test_sessions_returns_action(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/sessions")
        assert result.action == "sessions"
        assert result.should_quit is False


# ---------------------------------------------------------------------------
# /debug
# ---------------------------------------------------------------------------


class TestDebug:
    @pytest.mark.asyncio
    async def test_toggle_on(self) -> None:
        handler, state = _make_handler(debug=False)
        result = await handler.handle("/debug")
        assert state.debug is True
        assert "on" in result.message.lower()
        assert result.should_quit is False

    @pytest.mark.asyncio
    async def test_toggle_off(self) -> None:
        handler, state = _make_handler(debug=True)
        result = await handler.handle("/debug")
        assert state.debug is False
        assert "off" in result.message.lower()

    @pytest.mark.asyncio
    async def test_double_toggle(self) -> None:
        handler, state = _make_handler(debug=False)
        await handler.handle("/debug")
        assert state.debug is True
        await handler.handle("/debug")
        assert state.debug is False


# ---------------------------------------------------------------------------
# /help
# ---------------------------------------------------------------------------


class TestHelp:
    @pytest.mark.asyncio
    async def test_help_contains_commands(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/help")
        assert "/tools" in result.message
        assert "/model" in result.message
        assert "/quit" in result.message
        assert "/help" in result.message
        assert result.should_quit is False

    @pytest.mark.asyncio
    async def test_help_includes_streaming_commands(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/help")
        assert "/follow" in result.message
        assert "/abort" in result.message


# ---------------------------------------------------------------------------
# Unknown commands
# ---------------------------------------------------------------------------


class TestUnknownCommand:
    @pytest.mark.asyncio
    async def test_unknown_returns_error(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/foobar")
        assert "Unknown command" in result.message
        assert "/foobar" in result.message
        assert result.style == "warn"
        assert result.should_quit is False

    @pytest.mark.asyncio
    async def test_unknown_lists_known_commands(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/xyz")
        assert "/tools" in result.message
        assert "/quit" in result.message


# ---------------------------------------------------------------------------
# Edge cases / argument parsing
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_command_case_insensitive(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/HELP")
        assert "/tools" in result.message

    @pytest.mark.asyncio
    async def test_command_with_leading_spaces_in_arg(self) -> None:
        """Extra whitespace in the argument is stripped."""
        handler, state = _make_handler()
        await handler.handle("/model   some-model  ")
        assert state.model == "some-model"

    @pytest.mark.asyncio
    async def test_system_arg_preserves_internal_spaces(self) -> None:
        handler, state = _make_handler()
        await handler.handle("/system  hello   world  ")
        assert state.custom_system_prompt == "hello   world"

    @pytest.mark.asyncio
    async def test_quit_ignores_extra_args(self) -> None:
        handler, _ = _make_handler()
        result = await handler.handle("/quit now please")
        assert result.should_quit is True

    @pytest.mark.asyncio
    async def test_debug_ignores_extra_args(self) -> None:
        handler, state = _make_handler(debug=False)
        await handler.handle("/debug verbose")
        assert state.debug is True

    @pytest.mark.asyncio
    async def test_all_known_commands_return_command_result(self) -> None:
        """Smoke test: every known command returns a CommandResult."""
        handler, _ = _make_handler()
        commands = [
            "/tools",
            "/model test-m",
            "/system test-s",
            "/clear",
            "/compact",
            "/history",
            "/sessions",
            "/debug",
            "/help",
            "/quit",
        ]
        for cmd in commands:
            result = await handler.handle(cmd)
            assert isinstance(result, CommandResult), f"{cmd} did not return CommandResult"


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------


class TestConstants:
    def test_between_message_commands_non_empty(self) -> None:
        assert len(BETWEEN_MESSAGE_COMMANDS) > 0

    def test_during_streaming_commands_non_empty(self) -> None:
        assert len(DURING_STREAMING_COMMANDS) > 0

    def test_between_commands_contain_quit(self) -> None:
        assert any("/quit" in c for c in BETWEEN_MESSAGE_COMMANDS)

    def test_streaming_commands_contain_abort(self) -> None:
        assert any("/abort" in c for c in DURING_STREAMING_COMMANDS)
