"""Tests for CLI functionality."""

from __future__ import annotations

import pytest
import subprocess
import sys
from unittest.mock import patch

from isotope_agents.cli import create_parser, main


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