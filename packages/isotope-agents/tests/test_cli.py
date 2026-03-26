"""Tests for CLI functionality."""

from __future__ import annotations

import pytest
import subprocess
import sys
from unittest.mock import patch, MagicMock

from isotope_agents.cli import create_parser, handle_agent_event, main, list_sessions, run_rpc
from isotope_agents.session import SessionMeta
from isotope_core.types import (
    AssistantMessage,
    MessageUpdateEvent,
    TextContent,
    ToolEndEvent,
    ToolStartEvent,
    TurnEndEvent,
    Usage,
    UserMessage,
)


class TestCLI:
    """Tests for the CLI interface."""

    def test_parser_creation(self) -> None:
        """Parser can be created without errors."""
        parser = create_parser()
        assert parser is not None
        assert parser.prog == "isotope"

    def test_help_displays_correctly(self) -> None:
        """--help option works and exits with code 0."""
        parser = create_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--help"])
        assert exc_info.value.code == 0

    def test_version_displays_correctly(self) -> None:
        """--version option works and exits with code 0."""
        parser = create_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0

    def test_run_command_requires_prompt(self) -> None:
        """Run command requires a prompt argument."""
        parser = create_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["run"])
        assert exc_info.value.code != 0  # Should exit with error

    def test_run_command_parses_prompt(self) -> None:
        """Run command correctly parses prompt argument."""
        parser = create_parser()
        args = parser.parse_args(["run", "hello world"])
        assert args.command == "run"
        assert args.prompt == "hello world"

    def test_chat_command_parses(self) -> None:
        """Chat command parses correctly."""
        parser = create_parser()
        args = parser.parse_args(["chat"])
        assert args.command == "chat"

    def test_chat_command_with_session_flag(self) -> None:
        """Chat command with --session flag parses correctly."""
        parser = create_parser()
        args = parser.parse_args(["chat", "--session", "a1b2c3d4"])
        assert args.command == "chat"
        assert args.session == "a1b2c3d4"

    def test_sessions_command_parses(self) -> None:
        """Sessions command parses correctly."""
        parser = create_parser()
        args = parser.parse_args(["sessions"])
        assert args.command == "sessions"
        assert args.limit == 10  # default

    def test_sessions_command_with_limit(self) -> None:
        """Sessions command with --limit flag parses correctly."""
        parser = create_parser()
        args = parser.parse_args(["sessions", "--limit", "5"])
        assert args.command == "sessions"
        assert args.limit == 5

    def test_model_option_parsing(self) -> None:
        """Model option is parsed correctly."""
        parser = create_parser()
        args = parser.parse_args(["--model", "claude-opus-4.6", "chat"])
        assert args.model == "claude-opus-4.6"

    def test_preset_option_parsing(self) -> None:
        """Preset option is parsed correctly."""
        parser = create_parser()
        args = parser.parse_args(["--preset", "assistant", "chat"])
        assert args.preset == "assistant"

    def test_preset_option_validates(self) -> None:
        """Preset option validates choices."""
        parser = create_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--preset", "invalid", "chat"])
        assert exc_info.value.code != 0

    def test_no_tools_option_parsing(self) -> None:
        """--no-tools option is parsed correctly."""
        parser = create_parser()
        args = parser.parse_args(["--no-tools", "chat"])
        assert args.no_tools is True

    def test_default_values(self) -> None:
        """Default values are set correctly."""
        parser = create_parser()
        args = parser.parse_args(["chat"])
        assert args.model == "claude-opus-4.6"
        assert args.preset == "coding"
        assert args.no_tools is False

    def test_rpc_command_parses(self) -> None:
        """RPC command parses correctly."""
        parser = create_parser()
        args = parser.parse_args(["rpc"])
        assert args.command == "rpc"

    def test_rpc_command_with_session_flag(self) -> None:
        """RPC command with --session flag parses correctly."""
        parser = create_parser()
        args = parser.parse_args(["rpc", "--session", "abc123"])
        assert args.command == "rpc"
        assert args.session == "abc123"

    def test_rpc_command_with_preset(self) -> None:
        """RPC command with --preset flag parses correctly."""
        parser = create_parser()
        args = parser.parse_args(["--preset", "coding", "rpc"])
        assert args.command == "rpc"
        assert args.preset == "coding"

    def test_rpc_command_with_model(self) -> None:
        """RPC command with --model flag parses correctly."""
        parser = create_parser()
        args = parser.parse_args(["--model", "claude-sonnet-4-20250514", "rpc"])
        assert args.command == "rpc"
        assert args.model == "claude-sonnet-4-20250514"

    def test_rpc_command_with_all_flags(self) -> None:
        """RPC command with all flags parses correctly."""
        parser = create_parser()
        args = parser.parse_args([
            "--model", "claude-sonnet-4-20250514",
            "--preset", "assistant",
            "rpc",
            "--session", "xyz789",
        ])
        assert args.command == "rpc"
        assert args.model == "claude-sonnet-4-20250514"
        assert args.preset == "assistant"
        assert args.session == "xyz789"

    def test_rpc_appears_in_help(self) -> None:
        """RPC subcommand appears in help output."""
        parser = create_parser()
        help_text = parser.format_help()
        assert "rpc" in help_text

    def test_main_with_no_command_exits(self) -> None:
        """Main function exits when no command is provided."""
        with patch("sys.argv", ["isotope"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_with_help_exits_zero(self) -> None:
        """Main function exits with 0 for help."""
        with patch("sys.argv", ["isotope", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_main_with_version_exits_zero(self) -> None:
        """Main function exits with 0 for version."""
        with patch("sys.argv", ["isotope", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0


class TestSessionsCommand:
    """Tests for the sessions command."""

    @patch('isotope_agents.cli.SessionStore')
    def test_list_sessions_no_sessions(self, mock_session_store_class: MagicMock) -> None:
        """Test listing sessions when no sessions exist."""
        # Setup mock
        mock_session_store = MagicMock()
        mock_session_store_class.return_value = mock_session_store
        mock_session_store.list_sessions.return_value = []

        # Capture output
        with patch('builtins.print') as mock_print:
            list_sessions(10)

        mock_print.assert_called_with("No sessions found.")

    @patch('isotope_agents.cli.SessionStore')
    def test_list_sessions_with_sessions(self, mock_session_store_class: MagicMock) -> None:
        """Test listing sessions when sessions exist."""
        # Setup mock sessions
        mock_sessions = [
            SessionMeta(
                id="a1b2c3d4",
                started_at="2026-03-26T01:00:00Z",
                message_count=12,
                last_message_preview="fix the auth bug",
                model="claude-opus-4.6",
                preset="coding"
            ),
            SessionMeta(
                id="e5f6g7h8",
                started_at="2026-03-25T23:00:00Z",
                message_count=5,
                last_message_preview="summarize this doc",
                model="claude-opus-4.6",
                preset="assistant"
            )
        ]

        mock_session_store = MagicMock()
        mock_session_store_class.return_value = mock_session_store
        mock_session_store.list_sessions.return_value = mock_sessions

        # Capture output
        with patch('builtins.print') as mock_print:
            list_sessions(10)

        # Verify output calls
        calls = mock_print.call_args_list
        assert len(calls) >= 3  # Header, separator, and at least one session

        # Check header line
        header_call = calls[0][0][0]
        assert "ID" in header_call
        assert "Started" in header_call
        assert "Messages" in header_call
        assert "Last message" in header_call

    @patch('isotope_agents.cli.SessionStore')
    def test_list_sessions_respects_limit(self, mock_session_store_class: MagicMock) -> None:
        """Test that sessions listing respects the limit parameter."""
        # Create more sessions than the limit
        mock_sessions = [
            SessionMeta(f"session{i}", "2026-03-26T01:00:00Z", 1, f"message {i}", "claude-opus-4.6", "coding")
            for i in range(15)
        ]

        mock_session_store = MagicMock()
        mock_session_store_class.return_value = mock_session_store
        mock_session_store.list_sessions.return_value = mock_sessions

        with patch('builtins.print') as mock_print:
            list_sessions(5)

        # Check that only 5 sessions are printed (plus header and separator)
        calls = mock_print.call_args_list
        session_lines = [call for call in calls if 'session' in str(call)]
        assert len(session_lines) == 5


class TestHandleAgentEvent:
    """Tests for handle_agent_event() output routing."""

    def test_message_update_prints_delta(self, capsys: pytest.CaptureFixture[str]) -> None:
        """MessageUpdateEvent with delta prints content to stdout."""
        msg = AssistantMessage(
            content=[TextContent(text="hi")],
            timestamp=0,
        )
        event = MessageUpdateEvent(message=msg, delta="hello world")
        handle_agent_event(event)

        captured = capsys.readouterr()
        assert captured.out == "hello world"  # no trailing newline (end="")

    def test_message_update_no_delta_prints_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        """MessageUpdateEvent without delta prints nothing."""
        msg = AssistantMessage(content=[TextContent(text="")], timestamp=0)
        event = MessageUpdateEvent(message=msg, delta=None)
        handle_agent_event(event)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_tool_start_prints_tool_name(self, capsys: pytest.CaptureFixture[str]) -> None:
        """ToolStartEvent prints tool name to stderr."""
        event = ToolStartEvent(tool_call_id="tc1", tool_name="read_file", args={"path": "/a"})
        handle_agent_event(event)

        captured = capsys.readouterr()
        assert "[calling read_file]" in captured.err

    def test_tool_end_error_prints_error_marker(self, capsys: pytest.CaptureFixture[str]) -> None:
        """ToolEndEvent with is_error prints error marker to stderr."""
        event = ToolEndEvent(tool_call_id="tc1", tool_name="run", result="fail", is_error=True)
        handle_agent_event(event)

        captured = capsys.readouterr()
        assert "[tool error]" in captured.err

    def test_tool_end_success_prints_nothing(self, capsys: pytest.CaptureFixture[str]) -> None:
        """ToolEndEvent without error prints nothing."""
        event = ToolEndEvent(tool_call_id="tc1", tool_name="run", result="ok", is_error=False)
        handle_agent_event(event)

        captured = capsys.readouterr()
        assert captured.err == ""

    def test_turn_end_prints_newline_and_usage(self, capsys: pytest.CaptureFixture[str]) -> None:
        """TurnEndEvent with AssistantMessage prints newline and token usage."""
        msg = AssistantMessage(
            content=[TextContent(text="done")],
            usage=Usage(input_tokens=100, output_tokens=50),
            timestamp=0,
        )
        event = TurnEndEvent(message=msg)
        handle_agent_event(event)

        captured = capsys.readouterr()
        assert captured.out == "\n"
        assert "in=100" in captured.err
        assert "out=50" in captured.err

    def test_turn_end_non_assistant_message(self, capsys: pytest.CaptureFixture[str]) -> None:
        """TurnEndEvent with non-AssistantMessage prints newline only."""
        msg = UserMessage(content=[TextContent(text="hi")], timestamp=0)
        event = TurnEndEvent(message=msg)
        handle_agent_event(event)

        captured = capsys.readouterr()
        assert captured.out == "\n"
        # No usage line printed
        assert "tokens" not in captured.err

    def test_unknown_event_no_crash(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Unknown event types do not crash."""
        event = MagicMock()
        event.type = "some_future_event"
        handle_agent_event(event)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


class TestMainDispatch:
    """Tests for main() dispatching to correct subcommand handlers."""

    @patch("isotope_agents.cli.launch_tui")
    def test_main_chat_dispatches_to_launch_tui(self, mock_tui: MagicMock) -> None:
        """main() with 'chat' dispatches to launch_tui."""
        with patch("sys.argv", ["isotope", "chat"]):
            # chat path calls launch_tui without sys.exit, so it may or may not raise
            try:
                main()
            except SystemExit:
                pass
        mock_tui.assert_called_once()
        call_args = mock_tui.call_args
        assert call_args[0][0] == "claude-opus-4.6"  # model default
        assert call_args[0][1] == "coding"  # preset default
        assert call_args[0][2] is False  # no_tools default

    @patch("isotope_agents.cli.list_sessions")
    def test_main_sessions_dispatches_to_list_sessions(self, mock_ls: MagicMock) -> None:
        """main() with 'sessions' dispatches to list_sessions."""
        with patch("sys.argv", ["isotope", "sessions", "--limit", "3"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        mock_ls.assert_called_once_with(3)

    @patch("isotope_agents.cli.run_rpc")
    def test_main_rpc_dispatches_to_run_rpc(self, mock_rpc: MagicMock) -> None:
        """main() with 'rpc' dispatches to run_rpc."""
        with patch("sys.argv", ["isotope", "--model", "m1", "--preset", "minimal", "rpc", "--session", "s1"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        mock_rpc.assert_called_once_with("m1", "minimal", "s1")

    @patch("isotope_agents.cli.asyncio")
    def test_main_run_dispatches_asyncio_run(self, mock_asyncio: MagicMock) -> None:
        """main() with 'run' calls asyncio.run with run_one_shot coroutine."""
        with patch("sys.argv", ["isotope", "run", "hello"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
        mock_asyncio.run.assert_called_once()


class TestRunRpc:
    """Tests for run_rpc() wiring."""

    @patch("isotope_agents.cli.asyncio")
    @patch("isotope_agents.cli.RpcServer")
    @patch("isotope_agents.cli.IsotopeAgent")
    @patch("isotope_agents.cli.get_preset")
    @patch("isotope_agents.cli.ProxyProvider")
    @patch("isotope_agents.cli.load_config")
    def test_run_rpc_wires_agent_and_server(
        self,
        mock_load_config: MagicMock,
        mock_provider_cls: MagicMock,
        mock_get_preset: MagicMock,
        mock_agent_cls: MagicMock,
        mock_server_cls: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """run_rpc creates a ProxyProvider, IsotopeAgent, and RpcServer then runs it."""
        # Setup config mock
        mock_config = MagicMock()
        mock_config.model = "default"
        mock_config.provider.base_url = "http://localhost:4141"
        mock_config.provider.api_key = "test-key"
        mock_load_config.return_value = mock_config

        mock_preset = MagicMock()
        mock_get_preset.return_value = mock_preset

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        mock_server = MagicMock()
        mock_server_cls.return_value = mock_server

        run_rpc("claude-opus-4.6", "coding", session_id="sess1")

        # Provider created
        mock_provider_cls.assert_called_once()
        # Agent created with provider, preset, and session_id
        mock_agent_cls.assert_called_once()
        agent_kwargs = mock_agent_cls.call_args
        assert agent_kwargs.kwargs.get("session_id") == "sess1"
        # Server wraps agent
        mock_server_cls.assert_called_once_with(mock_agent)
        # asyncio.run called with server.run()
        mock_asyncio.run.assert_called_once_with(mock_server.run())

    @patch("isotope_agents.cli.asyncio")
    @patch("isotope_agents.cli.RpcServer")
    @patch("isotope_agents.cli.IsotopeAgent")
    @patch("isotope_agents.cli.get_preset")
    @patch("isotope_agents.cli.ProxyProvider")
    @patch("isotope_agents.cli.load_config")
    def test_run_rpc_cli_model_overrides_config(
        self,
        mock_load_config: MagicMock,
        mock_provider_cls: MagicMock,
        mock_get_preset: MagicMock,
        mock_agent_cls: MagicMock,
        mock_server_cls: MagicMock,
        mock_asyncio: MagicMock,
    ) -> None:
        """run_rpc uses CLI model when it differs from the default."""
        mock_config = MagicMock()
        mock_config.model = "config-model"
        mock_config.provider.base_url = "http://localhost:4141"
        mock_config.provider.api_key = None
        mock_load_config.return_value = mock_config

        run_rpc("claude-sonnet-4-20250514", "coding")

        # The CLI-specified model should be used (it's not DEFAULT_MODEL)
        provider_call = mock_provider_cls.call_args
        assert provider_call.kwargs.get("model") == "claude-sonnet-4-20250514"


class TestListSessionsEdgeCases:
    """Additional edge-case tests for list_sessions."""

    @patch("isotope_agents.cli.SessionStore")
    def test_long_preview_is_truncated(self, mock_store_cls: MagicMock, capsys: pytest.CaptureFixture[str]) -> None:
        """Session with long last_message_preview gets truncated with ellipsis."""
        long_preview = "a" * 60
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.list_sessions.return_value = [
            SessionMeta("id1", "2026-03-26T00:00:00Z", 1, long_preview, "m", "p"),
        ]

        list_sessions(10)

        captured = capsys.readouterr()
        # The code truncates at 40 chars and appends "..."
        assert "..." in captured.out
        assert "a" * 40 in captured.out

    @patch("isotope_agents.cli.SessionStore")
    def test_session_store_exception_exits(self, mock_store_cls: MagicMock) -> None:
        """list_sessions exits with 1 when SessionStore raises."""
        mock_store = MagicMock()
        mock_store_cls.return_value = mock_store
        mock_store.list_sessions.side_effect = RuntimeError("disk full")

        with pytest.raises(SystemExit) as exc_info:
            list_sessions(10)
        assert exc_info.value.code == 1


class TestCLIIntegration:
    """Integration tests for CLI (if tools are available)."""

    def test_cli_help_subprocess(self) -> None:
        """CLI help works via subprocess."""
        result = subprocess.run(
            [sys.executable, "-m", "isotope_agents", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "isotope" in result.stdout
        assert "Available commands" in result.stdout

    def test_cli_version_subprocess(self) -> None:
        """CLI version works via subprocess."""
        result = subprocess.run(
            [sys.executable, "-m", "isotope_agents", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "isotope-agents" in result.stdout

    def test_cli_no_command_shows_help(self) -> None:
        """CLI with no command shows help and exits with error."""
        result = subprocess.run(
            [sys.executable, "-m", "isotope_agents"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "usage:" in result.stdout or "usage:" in result.stderr

    def test_cli_run_missing_prompt_shows_error(self) -> None:
        """CLI run without prompt shows error."""
        result = subprocess.run(
            [sys.executable, "-m", "isotope_agents", "run"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
        # Should show error about missing prompt argument