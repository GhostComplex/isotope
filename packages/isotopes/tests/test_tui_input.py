"""Tests for isotopes.tui.input module.

Tests the StreamInputHandler class — stream input line parsing, prefill state
management, has_prompt_toolkit property, and headless prompt-toolkit app
creation using create_pipe_input / DummyOutput.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from isotopes.tui.input import StreamInputHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_agent() -> MagicMock:
    """Create a mock agent with follow_up, abort, and steer methods."""
    agent = MagicMock()
    agent.follow_up = MagicMock()
    agent.abort = MagicMock()
    agent.steer = MagicMock()
    return agent


def _noop_notice(*_args: object, **_kwargs: object) -> None:
    """No-op stand-in for print_stream_notice."""


# ---------------------------------------------------------------------------
# handle_stream_input_line — /follow <text>
# ---------------------------------------------------------------------------


class TestHandleFollow:
    def test_follow_with_text(self) -> None:
        handler = StreamInputHandler()
        agent = _make_agent()
        stop, steer = handler.handle_stream_input_line(
            "/follow do more work",
            agent,
            prompt_toolkit=False,
            print_stream_notice=_noop_notice,
        )
        agent.follow_up.assert_called_once_with("do more work")
        assert stop is False
        assert steer is None

    def test_follow_without_arg(self) -> None:
        handler = StreamInputHandler()
        agent = _make_agent()
        notices: list[str] = []

        def _capture(msg: str, **_kw: object) -> None:
            notices.append(msg)

        stop, steer = handler.handle_stream_input_line(
            "/follow",
            agent,
            prompt_toolkit=False,
            print_stream_notice=_capture,
        )
        agent.follow_up.assert_not_called()
        assert stop is False
        assert steer is None
        assert any("usage" in n.lower() for n in notices)


# ---------------------------------------------------------------------------
# handle_stream_input_line — /abort
# ---------------------------------------------------------------------------


class TestHandleAbort:
    def test_abort(self) -> None:
        handler = StreamInputHandler()
        agent = _make_agent()
        stop, steer = handler.handle_stream_input_line(
            "/abort",
            agent,
            prompt_toolkit=False,
            print_stream_notice=_noop_notice,
        )
        agent.abort.assert_called_once()
        assert stop is True
        assert steer is None


# ---------------------------------------------------------------------------
# handle_stream_input_line — plain text (steering)
# ---------------------------------------------------------------------------


class TestHandleSteer:
    def test_plain_text_steers(self) -> None:
        handler = StreamInputHandler()
        agent = _make_agent()
        stop, steer = handler.handle_stream_input_line(
            "change direction please",
            agent,
            prompt_toolkit=False,
            print_stream_notice=_noop_notice,
        )
        assert stop is True
        assert steer == "change direction please"

    def test_empty_input(self) -> None:
        handler = StreamInputHandler()
        agent = _make_agent()
        stop, steer = handler.handle_stream_input_line(
            "",
            agent,
            prompt_toolkit=False,
            print_stream_notice=_noop_notice,
        )
        assert stop is False
        assert steer is None

    def test_whitespace_only_input(self) -> None:
        handler = StreamInputHandler()
        agent = _make_agent()
        stop, steer = handler.handle_stream_input_line(
            "   ",
            agent,
            prompt_toolkit=False,
            print_stream_notice=_noop_notice,
        )
        assert stop is False
        assert steer is None


# ---------------------------------------------------------------------------
# handle_stream_input_line — unknown command
# ---------------------------------------------------------------------------


class TestHandleUnknownCommand:
    def test_unknown_slash_command(self) -> None:
        """An unrecognised /command does nothing (no crash, no steer)."""
        handler = StreamInputHandler()
        agent = _make_agent()
        stop, steer = handler.handle_stream_input_line(
            "/unknown",
            agent,
            prompt_toolkit=False,
            print_stream_notice=_noop_notice,
        )
        assert stop is False
        assert steer is None
        agent.follow_up.assert_not_called()
        agent.abort.assert_not_called()


# ---------------------------------------------------------------------------
# set_prefill_text / clear_prefill_text
# ---------------------------------------------------------------------------


class TestPrefillText:
    def test_set_and_read(self) -> None:
        handler = StreamInputHandler()
        assert handler._prefill_text == ""
        handler.set_prefill_text("hello")
        assert handler._prefill_text == "hello"

    def test_clear(self) -> None:
        handler = StreamInputHandler()
        handler.set_prefill_text("hello")
        handler.clear_prefill_text()
        assert handler._prefill_text == ""

    def test_set_overwrites(self) -> None:
        handler = StreamInputHandler()
        handler.set_prefill_text("first")
        handler.set_prefill_text("second")
        assert handler._prefill_text == "second"


# ---------------------------------------------------------------------------
# has_prompt_toolkit property
# ---------------------------------------------------------------------------


class TestHasPromptToolkit:
    def test_value_is_bool(self) -> None:
        handler = StreamInputHandler()
        assert isinstance(handler.has_prompt_toolkit, bool)

    def test_matches_module_constant(self) -> None:
        from isotopes.tui.input import HAS_PROMPT_TOOLKIT

        handler = StreamInputHandler()
        assert handler.has_prompt_toolkit is HAS_PROMPT_TOOLKIT


# ---------------------------------------------------------------------------
# prompt_toolkit integration — headless via create_pipe_input / DummyOutput
# ---------------------------------------------------------------------------

pt = pytest.importorskip("prompt_toolkit")


class TestCreateStreamPromptApp:
    """Test create_stream_prompt_app using headless prompt_toolkit I/O."""

    def test_app_creation(self) -> None:
        """Creating the app and buffer should not raise."""
        from prompt_toolkit.application import Application

        handler = StreamInputHandler()
        agent = _make_agent()
        app, buffer = handler.create_stream_prompt_app(agent)
        assert isinstance(app, Application)
        assert buffer is not None

    def test_prefill_appears_in_buffer(self) -> None:
        """Prefill text is carried into the new buffer."""
        handler = StreamInputHandler()
        handler.set_prefill_text("prefilled")
        agent = _make_agent()
        _app, buffer = handler.create_stream_prompt_app(agent)
        assert buffer.text == "prefilled"
        assert buffer.cursor_position == len("prefilled")

    @pytest.mark.asyncio
    async def test_typing_and_enter(self) -> None:
        """Simulate typing text + Enter — the app should return that text."""
        from prompt_toolkit.input.defaults import create_pipe_input
        from prompt_toolkit.output import DummyOutput

        handler = StreamInputHandler()
        agent = _make_agent()
        app, buffer = handler.create_stream_prompt_app(agent)

        with create_pipe_input() as pipe_input:
            app.input = pipe_input
            app.output = DummyOutput()

            pipe_input.send_text("hello world\r")
            result = await app.run_async()
            assert result == "hello world"
