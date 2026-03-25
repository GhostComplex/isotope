"""Tests for CLI functionality."""

from __future__ import annotations

import pytest
import subprocess
import sys
from unittest.mock import patch, MagicMock

from isotope_agents.cli import create_parser, main, list_sessions
from isotope_agents.session import SessionMeta


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