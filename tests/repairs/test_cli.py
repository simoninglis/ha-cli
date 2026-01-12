"""Tests for repairs CLI commands."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from ha_cli.domains.repairs.cli import _parse_repair_id, app

runner = CliRunner()


class TestParseRepairId:
    """Tests for _parse_repair_id helper."""

    def test_valid_format(self) -> None:
        """Test valid domain/issue_id format."""
        result = _parse_repair_id("homeassistant/deprecated_yaml")
        assert result == ("homeassistant", "deprecated_yaml")

    def test_valid_with_multiple_slashes(self) -> None:
        """Test issue_id containing slashes."""
        result = _parse_repair_id("domain/issue/with/slashes")
        assert result == ("domain", "issue/with/slashes")

    def test_invalid_no_slash(self) -> None:
        """Test invalid format without slash."""
        result = _parse_repair_id("no_slash_here")
        assert result is None

    def test_invalid_empty_domain(self) -> None:
        """Test invalid format with empty domain."""
        result = _parse_repair_id("/issue_id")
        assert result is None

    def test_invalid_empty_issue_id(self) -> None:
        """Test invalid format with empty issue_id."""
        result = _parse_repair_id("domain/")
        assert result is None

    def test_strips_whitespace(self) -> None:
        """Test whitespace is stripped."""
        result = _parse_repair_id("  domain / issue_id  ")
        assert result == ("domain", "issue_id")

    def test_empty_string(self) -> None:
        """Test empty string."""
        result = _parse_repair_id("")
        assert result is None

    def test_only_slash(self) -> None:
        """Test string with only slash."""
        result = _parse_repair_id("/")
        assert result is None


class TestListCommand:
    """Tests for repairs list command."""

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_list_repairs_success(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test listing repairs successfully."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={
            "issues": [
                {
                    "domain": "homeassistant",
                    "issue_id": "deprecated_yaml",
                    "severity": "warning",
                    "active": True,
                    "is_fixable": True,
                },
                {
                    "domain": "zwave_js",
                    "issue_id": "node_not_ready",
                    "severity": "error",
                    "active": True,
                    "is_fixable": False,
                },
            ]
        })
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "Home Assistant Repairs" in result.stdout
        assert "homeassistant" in result.stdout
        assert "zwave_js" in result.stdout

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_list_repairs_empty(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test listing repairs when none exist."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={"issues": []})
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "No active repairs found" in result.stdout

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_list_repairs_json(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test listing repairs with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={
            "issues": [
                {
                    "domain": "homeassistant",
                    "issue_id": "test",
                    "severity": "warning",
                    "active": True,
                }
            ]
        })
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["list", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["domain"] == "homeassistant"

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_list_repairs_porcelain(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test listing repairs with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={
            "issues": [
                {
                    "domain": "homeassistant",
                    "issue_id": "test",
                    "severity": "warning",
                    "active": True,
                    "is_fixable": True,
                }
            ]
        })
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["list", "--porcelain"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "success"
        assert data["command"] == "repairs list"
        assert "data" in data
        assert "metadata" in data
        assert data["metadata"]["total_count"] == 1
        assert data["metadata"]["fixable_count"] == 1

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_list_repairs_include_ignored(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test listing repairs with --all flag includes ignored."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={
            "issues": [
                {
                    "domain": "homeassistant",
                    "issue_id": "active",
                    "severity": "warning",
                    "active": True,
                },
                {
                    "domain": "homeassistant",
                    "issue_id": "ignored",
                    "severity": "warning",
                    "active": False,
                },
            ]
        })
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["list", "--all", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert len(data) == 2


class TestShowCommand:
    """Tests for repairs show command."""

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_show_repair_success(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test showing a specific repair."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={
            "issues": [
                {
                    "domain": "homeassistant",
                    "issue_id": "deprecated_yaml",
                    "severity": "warning",
                    "active": True,
                    "is_fixable": True,
                    "is_persistent": False,
                }
            ]
        })
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["show", "homeassistant/deprecated_yaml"])

        assert result.exit_code == 0
        assert "homeassistant/deprecated_yaml" in result.stdout
        assert "WARNING" in result.stdout

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_show_repair_not_found(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test showing a repair that doesn't exist."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={"issues": []})
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["show", "nonexistent/repair"])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_show_repair_invalid_format(self) -> None:
        """Test showing with invalid repair ID format."""
        result = runner.invoke(app, ["show", "invalid_format"])

        assert result.exit_code == 1
        assert "Invalid repair ID format" in result.stdout

    def test_show_repair_empty_domain(self) -> None:
        """Test showing with empty domain in ID."""
        result = runner.invoke(app, ["show", "/issue_id"])

        assert result.exit_code == 1
        assert "Invalid repair ID format" in result.stdout

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_show_repair_json(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test showing repair with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={
            "issues": [
                {
                    "domain": "homeassistant",
                    "issue_id": "test",
                    "severity": "warning",
                    "active": True,
                }
            ]
        })
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["show", "homeassistant/test", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["domain"] == "homeassistant"
        assert data["issue_id"] == "test"

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_show_repair_porcelain(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test showing repair with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={
            "issues": [
                {
                    "domain": "homeassistant",
                    "issue_id": "test",
                    "severity": "warning",
                    "active": True,
                }
            ]
        })
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["show", "homeassistant/test", "--porcelain"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "success"
        assert data["command"] == "repairs show"
        assert data["metadata"]["repair_id"] == "homeassistant/test"

    def test_show_repair_porcelain_invalid_format(self) -> None:
        """Test porcelain error output for invalid format."""
        result = runner.invoke(app, ["show", "invalid", "--porcelain"])

        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["status"] == "error"
        assert data["error"]["code"] == "INVALID_FORMAT"


class TestIgnoreCommand:
    """Tests for repairs ignore command."""

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_ignore_repair_success(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test ignoring a repair successfully."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        # First call returns the repair (for existence check)
        # Second call is the ignore action
        mock_client._ws_call = AsyncMock(side_effect=[
            {
                "issues": [
                    {
                        "domain": "homeassistant",
                        "issue_id": "test",
                        "severity": "warning",
                        "active": True,
                    }
                ]
            },
            None,  # ignore call returns nothing
        ])
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["ignore", "homeassistant/test"])

        assert result.exit_code == 0
        assert "Ignored repair" in result.stdout

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_ignore_repair_not_found(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test ignoring a repair that doesn't exist."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={"issues": []})
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["ignore", "nonexistent/repair"])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_ignore_repair_invalid_format(self) -> None:
        """Test ignoring with invalid repair ID format."""
        result = runner.invoke(app, ["ignore", "invalid"])

        assert result.exit_code == 1
        assert "Invalid repair ID format" in result.stdout

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_ignore_repair_porcelain(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test ignoring repair with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(side_effect=[
            {
                "issues": [
                    {
                        "domain": "homeassistant",
                        "issue_id": "test",
                        "severity": "warning",
                        "active": True,
                    }
                ]
            },
            None,
        ])
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["ignore", "homeassistant/test", "--porcelain"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "success"
        assert data["command"] == "repairs ignore"
        assert data["data"]["ignored"] is True

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_ignore_repair_porcelain_not_found(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test porcelain error output when repair not found."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={"issues": []})
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["ignore", "nonexistent/repair", "--porcelain"])

        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["status"] == "error"
        assert data["error"]["code"] == "NOT_FOUND"


class TestUnignoreCommand:
    """Tests for repairs unignore command."""

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_unignore_repair_success(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test unignoring a repair successfully."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(side_effect=[
            {
                "issues": [
                    {
                        "domain": "homeassistant",
                        "issue_id": "test",
                        "severity": "warning",
                        "active": False,  # ignored
                    }
                ]
            },
            None,
        ])
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["unignore", "homeassistant/test"])

        assert result.exit_code == 0
        assert "Unignored repair" in result.stdout

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_unignore_repair_not_found(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test unignoring a repair that doesn't exist."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={"issues": []})
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["unignore", "nonexistent/repair"])

        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    def test_unignore_repair_invalid_format(self) -> None:
        """Test unignoring with invalid repair ID format."""
        result = runner.invoke(app, ["unignore", "invalid"])

        assert result.exit_code == 1
        assert "Invalid repair ID format" in result.stdout

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_unignore_repair_porcelain(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test unignoring repair with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(side_effect=[
            {
                "issues": [
                    {
                        "domain": "homeassistant",
                        "issue_id": "test",
                        "severity": "warning",
                        "active": False,
                    }
                ]
            },
            None,
        ])
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["unignore", "homeassistant/test", "--porcelain"])

        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["status"] == "success"
        assert data["command"] == "repairs unignore"
        assert data["data"]["ignored"] is False

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_unignore_repair_porcelain_not_found(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test porcelain error output when repair not found."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={"issues": []})
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["unignore", "nonexistent/repair", "--porcelain"])

        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["status"] == "error"
        assert data["error"]["code"] == "NOT_FOUND"


class TestVersionCommand:
    """Tests for repairs version command."""

    def test_version(self) -> None:
        """Test version command output."""
        result = runner.invoke(app, ["version"])

        assert result.exit_code == 0
        assert "ha-cli repairs version" in result.stdout


class TestSeverityDisplay:
    """Tests for severity display formatting."""

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_severity_colors_in_output(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test that severity levels are displayed correctly."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={
            "issues": [
                {
                    "domain": "test",
                    "issue_id": "critical_issue",
                    "severity": "critical",
                    "active": True,
                },
                {
                    "domain": "test",
                    "issue_id": "error_issue",
                    "severity": "error",
                    "active": True,
                },
                {
                    "domain": "test",
                    "issue_id": "warning_issue",
                    "severity": "warning",
                    "active": True,
                },
            ]
        })
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        # Check severity labels are present (uppercase in table)
        assert "CRITICAL" in result.stdout
        assert "ERROR" in result.stdout
        assert "WARNING" in result.stdout


class TestFixableDisplay:
    """Tests for fixable flag display."""

    @patch("ha_cli.domains.repairs.cli.get_client_config")
    @patch("ha_cli.domains.repairs.cli.HAClient")
    def test_fixable_yes_no_dash(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test fixable displays Yes/No/- for True/False/None."""
        mock_config.return_value = ("http://test:8123", "test-token")

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client._ws_call = AsyncMock(return_value={
            "issues": [
                {
                    "domain": "test",
                    "issue_id": "fixable_true",
                    "severity": "warning",
                    "active": True,
                    "is_fixable": True,
                },
                {
                    "domain": "test",
                    "issue_id": "fixable_false",
                    "severity": "warning",
                    "active": True,
                    "is_fixable": False,
                },
                {
                    "domain": "test",
                    "issue_id": "fixable_none",
                    "severity": "warning",
                    "active": True,
                    # is_fixable not present = None
                },
            ]
        })
        mock_client_class.return_value = mock_client

        result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        # The table should show Yes, No, and - for the three cases
        # Due to table formatting, just check the outputs contain expected values
        output = result.stdout
        assert "Yes" in output
        assert "No" in output
        # Check for dash (unknown fixable) - appears in Fixable column
        assert "-" in output or "│ - │" in output
