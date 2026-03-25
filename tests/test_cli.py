"""Tests for isotope-agents CLI."""

from __future__ import annotations

from click.testing import CliRunner

from isotope_agents.cli import main


class TestCLI:
    """CLI smoke tests."""

    def test_main_help(self) -> None:
        """Main command shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Isotope" in result.output

    def test_chat_help(self) -> None:
        """Chat command shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--help"])
        assert result.exit_code == 0
        assert "--preset" in result.output
        assert "--model" in result.output

    def test_run_help(self) -> None:
        """Run command shows help."""
        runner = CliRunner()
        result = runner.invoke(main, ["run", "--help"])
        assert result.exit_code == 0
        assert "--preset" in result.output
        assert "--print" in result.output

    def test_version(self) -> None:
        """Version flag works."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output or "version" in result.output.lower()

    def test_unknown_command(self) -> None:
        """Unknown commands show error."""
        runner = CliRunner()
        result = runner.invoke(main, ["nonexistent"])
        assert result.exit_code != 0
