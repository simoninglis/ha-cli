"""Tests for main CLI entry point (ha_cli/cli.py)."""

import re

from typer.testing import CliRunner

from ha_cli.cli import app

runner = CliRunner()


class TestMainCLI:
    """Test main CLI commands."""

    def test_version_command(self) -> None:
        """Test version command shows version info."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "ha-cli version" in result.stdout

    def test_no_args_shows_help(self) -> None:
        """Test invoking with no args shows help or error."""
        result = runner.invoke(app, [])
        # Typer may return 0 or 2 depending on configuration
        # Either is acceptable as long as help/usage is shown
        assert result.exit_code in [0, 2]
        # Should show usage info - check stdout or stderr
        output = result.stdout + (result.stderr or "")
        assert (
            "ha-cli" in output.lower()
            or "usage" in output.lower()
            or "commands" in output.lower()
        )

    def test_help_option(self) -> None:
        """Test --help option."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Multi-domain command-line tool" in result.stdout

    def test_audit_subcommand_available(self) -> None:
        """Test audit subcommand is registered."""
        result = runner.invoke(app, ["audit", "--help"])
        assert result.exit_code == 0
        assert "Audit Home Assistant" in result.stdout

    def test_automations_subcommand_available(self) -> None:
        """Test automations subcommand is registered."""
        result = runner.invoke(app, ["automations", "--help"])
        assert result.exit_code == 0
        assert "automations" in result.stdout.lower()

    def test_dashboards_subcommand_available(self) -> None:
        """Test dashboards subcommand is registered."""
        result = runner.invoke(app, ["dashboards", "--help"])
        assert result.exit_code == 0
        assert "dashboard" in result.stdout.lower()

    def test_entities_subcommand_available(self) -> None:
        """Test entities subcommand is registered."""
        result = runner.invoke(app, ["entities", "--help"])
        assert result.exit_code == 0
        assert "entit" in result.stdout.lower()

    def test_invalid_command(self) -> None:
        """Test invalid command shows error."""
        result = runner.invoke(app, ["nonexistent"])
        assert result.exit_code != 0


class TestLiteralTokenRefused:
    """--token names an env var. A literal token is a usage error that never echoes it."""

    LITERAL = "eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJ4In0.c2lnbmF0dXJl"

    def test_literal_token_is_a_usage_error(self) -> None:
        result = runner.invoke(app, ["areas", "list", "--url", "http://ha.local:8123", "--token", self.LITERAL])
        flat = " ".join(re.sub(r"[│╭╮╰╯─]", " ", result.output).split())   # rich wraps it in a box
        assert result.exit_code == 2
        assert "NAME of an environment variable" in flat
        assert self.LITERAL not in result.output
        assert self.LITERAL not in flat
