"""Tests for system CLI commands (ha_cli/domains/system/cli.py)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_cli.cli import app
from ha_cli.domains.system.service import SSHError, SystemInfo

runner = CliRunner()


class TestSystemRestart:
    """Test system restart command."""

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_restart_success(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test successful restart."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.check_config = AsyncMock(return_value=(True, "Config valid"))
        mock_service.restart = AsyncMock(return_value=(True, "Restart initiated"))

        result = runner.invoke(app, ["system", "restart"])
        assert result.exit_code == 0
        assert "restarted successfully" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_restart_no_check(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test restart with --no-check."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.restart = AsyncMock(return_value=(True, "Restart initiated"))

        result = runner.invoke(app, ["system", "restart", "--no-check"])
        assert result.exit_code == 0
        # check_config should not be called
        mock_service.check_config.assert_not_called()

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_restart_config_invalid(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test restart aborted when config is invalid."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.check_config = AsyncMock(
            return_value=(False, "Invalid config at line 42")
        )

        result = runner.invoke(app, ["system", "restart"])
        assert result.exit_code != 0
        assert "invalid" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_restart_ssh_error_with_api_fallback(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test restart continues when SSH check fails but API available."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.check_config = AsyncMock(
            side_effect=SSHError("Connection refused", returncode=255)
        )
        mock_service.restart = AsyncMock(return_value=(True, "Restart via API"))

        result = runner.invoke(app, ["system", "restart"])
        assert result.exit_code == 0
        assert "skipped" in result.stdout.lower()
        assert "restarted" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_restart_json_output(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test restart with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.check_config = AsyncMock(return_value=(True, "Config valid"))
        mock_service.restart = AsyncMock(return_value=(True, "Restart initiated"))

        result = runner.invoke(app, ["system", "restart", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert output["action"] == "restart"

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_restart_porcelain_output(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test restart with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.check_config = AsyncMock(return_value=(True, "Config valid"))
        mock_service.restart = AsyncMock(return_value=(True, "Restart initiated"))

        result = runner.invoke(app, ["system", "restart", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert "data" in output


class TestSystemReload:
    """Test system reload command."""

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_reload_automations(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test reload automations."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.reload = AsyncMock(
            return_value=(True, "Reloaded automations successfully")
        )

        result = runner.invoke(app, ["system", "reload", "automations"])
        assert result.exit_code == 0
        assert "automations" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_reload_default(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test reload without component."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.reload = AsyncMock(
            return_value=(True, "Reloaded: automation, script, scene")
        )

        result = runner.invoke(app, ["system", "reload"])
        assert result.exit_code == 0
        mock_service.reload.assert_called_once_with(None)

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_reload_failure(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test reload failure."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.reload = AsyncMock(
            return_value=(False, "Unknown component: invalid")
        )

        result = runner.invoke(app, ["system", "reload", "invalid"])
        assert result.exit_code != 0
        assert "Unknown component" in result.stdout


class TestSystemCheck:
    """Test system check command."""

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_check_valid(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test check with valid config."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.check_config = AsyncMock(
            return_value=(True, "Configuration valid!")
        )

        result = runner.invoke(app, ["system", "check"])
        assert result.exit_code == 0
        assert "valid" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_check_invalid(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test check with invalid config."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.check_config = AsyncMock(
            return_value=(False, "Invalid config at line 42")
        )

        result = runner.invoke(app, ["system", "check"])
        assert result.exit_code != 0
        assert "invalid" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_check_ssh_error(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test check with SSH error."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.check_config = AsyncMock(
            side_effect=SSHError("Connection refused", returncode=255)
        )

        result = runner.invoke(app, ["system", "check"])
        assert result.exit_code != 0
        assert "ssh" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_check_json_output(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test check with JSON output."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.check_config = AsyncMock(
            return_value=(True, "Configuration valid!")
        )

        result = runner.invoke(app, ["system", "check", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["valid"] is True


class TestSystemLogs:
    """Test system logs command."""

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_logs_default(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test logs with defaults."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs = AsyncMock(
            return_value="2025-12-11 INFO Starting Home Assistant"
        )

        result = runner.invoke(app, ["system", "logs"])
        assert result.exit_code == 0
        mock_service.get_logs.assert_called_once_with(
            lines=100,
            filter_pattern=None,
            errors_only=False,
        )

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_logs_with_lines(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test logs with custom lines."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs = AsyncMock(return_value="Log output")

        result = runner.invoke(app, ["system", "logs", "--lines", "50"])
        assert result.exit_code == 0
        mock_service.get_logs.assert_called_once_with(
            lines=50,
            filter_pattern=None,
            errors_only=False,
        )

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_logs_with_filter(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test logs with filter pattern."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs = AsyncMock(return_value="Error: something failed")

        result = runner.invoke(app, ["system", "logs", "--filter", "error"])
        assert result.exit_code == 0
        mock_service.get_logs.assert_called_once_with(
            lines=100,
            filter_pattern="error",
            errors_only=False,
        )

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_logs_errors_only(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test logs with --errors-only."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs = AsyncMock(return_value="Error log from API")

        result = runner.invoke(app, ["system", "logs", "--errors-only"])
        assert result.exit_code == 0
        mock_service.get_logs.assert_called_once_with(
            lines=100,
            filter_pattern=None,
            errors_only=True,
        )

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_logs_ssh_error(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test logs with SSH error."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs = AsyncMock(
            side_effect=SSHError("Connection refused", returncode=255)
        )

        result = runner.invoke(app, ["system", "logs"])
        assert result.exit_code != 0
        assert "ssh" in result.stdout.lower()
        assert "errors-only" in result.stdout.lower()  # Should suggest alternative

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_logs_raw_output(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test logs with raw output."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        log_content = "2025-12-11 INFO Starting\n2025-12-11 INFO Ready"
        mock_service.get_logs = AsyncMock(return_value=log_content)

        result = runner.invoke(app, ["system", "logs", "--raw"])
        assert result.exit_code == 0
        # Raw output should not have panel formatting
        assert "Starting" in result.stdout
        assert "Ready" in result.stdout

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_logs_json_output(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test logs with JSON output."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_logs = AsyncMock(return_value="Line 1\nLine 2\nLine 3")

        result = runner.invoke(app, ["system", "logs", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert "logs" in output
        assert len(output["logs"]) == 3


class TestSystemInfo:
    """Test system info command."""

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_info_success(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test info success."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_info = AsyncMock(
            return_value=SystemInfo(
                version="2025.12.1",
                installation_type="Home Assistant OS",
                host="homeassistant.local",
            )
        )

        result = runner.invoke(app, ["system", "info"])
        assert result.exit_code == 0
        assert "2025.12.1" in result.stdout
        assert "Home Assistant OS" in result.stdout

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_info_failure(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test info failure."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_info = AsyncMock(return_value=None)

        result = runner.invoke(app, ["system", "info"])
        assert result.exit_code != 0
        assert "failed" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_info_json_output(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test info with JSON output."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_info = AsyncMock(
            return_value=SystemInfo(
                version="2025.12.1",
                installation_type="Home Assistant OS",
                host="homeassistant.local",
            )
        )

        result = runner.invoke(app, ["system", "info", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["version"] == "2025.12.1"
        assert output["installation_type"] == "Home Assistant OS"

    @patch("ha_cli.domains.system.cli.SystemService")
    def test_info_porcelain_output(
        self,
        mock_service_class: MagicMock,
    ) -> None:
        """Test info with porcelain output."""
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_info = AsyncMock(
            return_value=SystemInfo(
                version="2025.12.1",
                installation_type="Home Assistant OS",
                host="homeassistant.local",
            )
        )

        result = runner.invoke(app, ["system", "info", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["data"]["version"] == "2025.12.1"


class TestSystemCall:
    """Test system call (service call) command."""

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_call_basic(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test basic service call."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.call_service = AsyncMock(return_value={"success": True})

        result = runner.invoke(app, ["system", "call", "light.turn_on"])
        assert result.exit_code == 0
        assert "successfully" in result.stdout.lower()
        mock_service.call_service.assert_called_once_with(
            domain="light",
            service="turn_on",
            entity_ids=None,
            service_data=None,
            return_response=False,
        )

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_call_with_entity(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test service call with entity target."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.call_service = AsyncMock(return_value={"success": True})

        result = runner.invoke(
            app, ["system", "call", "light.turn_on", "--entity", "light.office"]
        )
        assert result.exit_code == 0
        mock_service.call_service.assert_called_once_with(
            domain="light",
            service="turn_on",
            entity_ids=["light.office"],
            service_data=None,
            return_response=False,
        )

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_call_with_multiple_entities(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test service call with multiple entity targets."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.call_service = AsyncMock(return_value={"success": True})

        result = runner.invoke(
            app,
            [
                "system", "call", "light.turn_on",
                "--entity", "light.office",
                "--entity", "light.kitchen",
            ],
        )
        assert result.exit_code == 0
        mock_service.call_service.assert_called_once_with(
            domain="light",
            service="turn_on",
            entity_ids=["light.office", "light.kitchen"],
            service_data=None,
            return_response=False,
        )

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_call_with_data(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test service call with JSON data."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.call_service = AsyncMock(return_value={"success": True})

        result = runner.invoke(
            app,
            [
                "system", "call", "climate.set_temperature",
                "--entity", "climate.lounge",
                "--data", '{"temperature": 22}',
            ],
        )
        assert result.exit_code == 0
        mock_service.call_service.assert_called_once_with(
            domain="climate",
            service="set_temperature",
            entity_ids=["climate.lounge"],
            service_data={"temperature": 22},
            return_response=False,
        )

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_call_json_output(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test service call with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.call_service = AsyncMock(return_value={"success": True})

        result = runner.invoke(
            app, ["system", "call", "light.turn_on", "--json"]
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert output["domain"] == "light"
        assert output["service"] == "turn_on"

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_call_porcelain_output(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test service call with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.call_service = AsyncMock(return_value={"success": True})

        result = runner.invoke(
            app, ["system", "call", "light.turn_on", "--entity", "light.office", "--porcelain"]
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["data"]["domain"] == "light"
        assert output["data"]["service"] == "turn_on"
        assert "light.office" in output["data"]["entities"]

    def test_call_invalid_service_format(self) -> None:
        """Test error on invalid service format."""
        result = runner.invoke(app, ["system", "call", "invalid_service"])
        assert result.exit_code != 0
        assert "Invalid service format" in result.stdout

    def test_call_invalid_json_data(self) -> None:
        """Test error on invalid JSON data."""
        result = runner.invoke(
            app, ["system", "call", "light.turn_on", "--data", "not valid json"]
        )
        assert result.exit_code != 0
        assert "Invalid JSON" in result.stdout

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_call_service_failure(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test service call failure handling."""
        from ha_cli.common.exceptions import HAAutomationError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.call_service = AsyncMock(
            side_effect=HAAutomationError("Service not found")
        )

        result = runner.invoke(app, ["system", "call", "invalid.service"])
        assert result.exit_code != 0
        assert "failed" in result.stdout.lower()


class TestSystemTemplate:
    """Test system template (Jinja2 evaluation) command."""

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_template_basic(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test basic template evaluation."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.render_template = AsyncMock(return_value="2025-12-16 10:00:00")

        result = runner.invoke(app, ["system", "template", "{{ now() }}"])
        assert result.exit_code == 0
        assert "2025-12-16 10:00:00" in result.stdout
        mock_service.render_template.assert_called_once_with("{{ now() }}")

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_template_raw_output(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test template with raw output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.render_template = AsyncMock(return_value="on")

        result = runner.invoke(
            app, ["system", "template", "{{ states('light.office') }}", "--raw"]
        )
        assert result.exit_code == 0
        # Raw should output just the result
        assert result.stdout.strip() == "on"

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_template_json_output(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test template with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.render_template = AsyncMock(return_value="test result")

        result = runner.invoke(
            app, ["system", "template", "{{ now() }}", "--json"]
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["success"] is True
        assert output["result"] == "test result"
        assert output["template"] == "{{ now() }}"

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_template_porcelain_output(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test template with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.render_template = AsyncMock(return_value="42")

        result = runner.invoke(
            app, ["system", "template", "{{ 40 + 2 }}", "--porcelain"]
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["data"]["result"] == "42"
        assert output["data"]["template"] == "{{ 40 + 2 }}"
        assert "metadata" in output

    def test_template_no_input(self) -> None:
        """Test error when no template provided."""
        result = runner.invoke(app, ["system", "template"])
        assert result.exit_code != 0
        assert "Must provide template argument or --file" in result.stdout

    def test_template_both_arg_and_file(self) -> None:
        """Test error when both template arg and --file provided."""
        result = runner.invoke(
            app, ["system", "template", "{{ now() }}", "--file", "test.j2"]
        )
        assert result.exit_code != 0
        assert "Cannot use both template argument and --file" in result.stdout

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_template_error(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test template rendering error."""
        from ha_cli.common.exceptions import HAAutomationError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.render_template = AsyncMock(
            side_effect=HAAutomationError("Undefined variable 'foo'")
        )

        result = runner.invoke(app, ["system", "template", "{{ foo }}"])
        assert result.exit_code != 0
        assert "failed" in result.stdout.lower()


class TestSystemIntegrations:
    """Test system integrations command."""

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_list_all(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test listing all integrations."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(
            return_value=[
                {
                    "entry_id": "abc123",
                    "domain": "sonos",
                    "title": "Living Room Speaker",
                    "state": "loaded",
                    "disabled_by": None,
                },
                {
                    "entry_id": "def456",
                    "domain": "zha",
                    "title": "Zigbee Coordinator",
                    "state": "loaded",
                    "disabled_by": None,
                },
            ]
        )

        result = runner.invoke(app, ["system", "integrations"])
        assert result.exit_code == 0
        assert "sonos" in result.stdout
        assert "zha" in result.stdout
        assert "loaded" in result.stdout
        mock_service.get_integrations.assert_called_once_with(
            domain=None,
            unhealthy_only=False,
        )

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_filter_by_domain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test filtering integrations by domain."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(
            return_value=[
                {
                    "entry_id": "abc123",
                    "domain": "sonos",
                    "title": "Living Room Speaker",
                    "state": "loaded",
                    "disabled_by": None,
                },
            ]
        )

        result = runner.invoke(app, ["system", "integrations", "--domain", "sonos"])
        assert result.exit_code == 0
        mock_service.get_integrations.assert_called_once_with(
            domain="sonos",
            unhealthy_only=False,
        )

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_unhealthy_only(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test filtering for unhealthy integrations only."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(
            return_value=[
                {
                    "entry_id": "ghi789",
                    "domain": "broken_integration",
                    "title": "Broken",
                    "state": "setup_error",
                    "disabled_by": None,
                },
            ]
        )

        result = runner.invoke(app, ["system", "integrations", "--unhealthy"])
        assert result.exit_code == 0
        mock_service.get_integrations.assert_called_once_with(
            domain=None,
            unhealthy_only=True,
        )

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_no_unhealthy_shows_healthy_message(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test that no unhealthy integrations shows healthy message."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(return_value=[])

        result = runner.invoke(app, ["system", "integrations", "--unhealthy"])
        assert result.exit_code == 0
        assert "no unhealthy" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_empty_with_domain_filter_shows_domain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test that empty results with domain filter shows the domain in message."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(return_value=[])

        result = runner.invoke(
            app, ["system", "integrations", "--domain", "nonexistent"]
        )
        assert result.exit_code == 0
        assert "nonexistent" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_json_output(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test integrations with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(
            return_value=[
                {
                    "entry_id": "abc123",
                    "domain": "sonos",
                    "title": "Living Room",
                    "state": "loaded",
                    "disabled_by": None,
                },
            ]
        )

        result = runner.invoke(app, ["system", "integrations", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert "integrations" in output
        assert output["count"] == 1
        assert output["state_summary"]["loaded"] == 1
        assert output["integrations"][0]["domain"] == "sonos"

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_porcelain_output(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test integrations with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(
            return_value=[
                {
                    "entry_id": "abc123",
                    "domain": "zha",
                    "title": "Zigbee",
                    "state": "loaded",
                    "disabled_by": None,
                },
            ]
        )

        result = runner.invoke(app, ["system", "integrations", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["data"]["count"] == 1
        assert "metadata" in output
        assert "suggestions" in output

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_error_handling(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test integrations error handling."""
        from ha_cli.common.exceptions import EXIT_HA_ERROR, HAAutomationError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(
            side_effect=HAAutomationError("Connection failed")
        )

        result = runner.invoke(app, ["system", "integrations"])
        assert result.exit_code == EXIT_HA_ERROR
        assert "failed" in result.stdout.lower()

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_error_porcelain_preserves_details(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test that porcelain error output preserves HAAutomationError.details."""
        from ha_cli.common.exceptions import EXIT_HA_ERROR, HAAutomationError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(
            side_effect=HAAutomationError(
                "Unexpected response",
                details={"result_type": "dict", "extra": "info"},
            )
        )

        result = runner.invoke(app, ["system", "integrations", "--porcelain"])
        assert result.exit_code == EXIT_HA_ERROR
        output = json.loads(result.stdout)
        assert output["status"] == "error"
        assert "Unexpected response" in output["error"]["message"]
        # Verify details are preserved
        assert output["error"]["details"]["result_type"] == "dict"
        assert output["error"]["details"]["extra"] == "info"

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_error_json_preserves_details(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test that JSON error output preserves HAAutomationError.details."""
        from ha_cli.common.exceptions import EXIT_HA_ERROR, HAAutomationError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(
            side_effect=HAAutomationError(
                "API error",
                details={"code": "WS_ERROR", "status": 500},
            )
        )

        result = runner.invoke(app, ["system", "integrations", "--json"])
        assert result.exit_code == EXIT_HA_ERROR
        output = json.loads(result.stdout)
        assert output["success"] is False
        assert "API error" in output["error"]
        # Verify details are preserved
        assert output["details"]["code"] == "WS_ERROR"
        assert output["details"]["status"] == 500

    @patch("ha_cli.domains.system.cli.get_client_config")
    @patch("ha_cli.domains.system.cli.HAClient")
    @patch("ha_cli.domains.system.cli.SystemService")
    def test_integrations_mixed_states(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test integrations with mixed states show unhealthy first."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_class.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_integrations = AsyncMock(
            return_value=[
                {
                    "entry_id": "abc",
                    "domain": "good",
                    "title": "Good Integration",
                    "state": "loaded",
                    "disabled_by": None,
                },
                {
                    "entry_id": "def",
                    "domain": "bad",
                    "title": "Bad Integration",
                    "state": "setup_error",
                    "disabled_by": None,
                },
            ]
        )

        result = runner.invoke(app, ["system", "integrations"])
        assert result.exit_code == 0
        # setup_error should appear before loaded in output
        # Use newline-prefix to avoid substring matches (e.g., "not_loaded" contains "loaded")
        stdout = result.stdout
        error_pos = stdout.find("setup_error")
        # Look for "loaded" as a state heading (with newline prefix to avoid "not_loaded")
        loaded_heading_pos = stdout.find("\nloaded") if "\nloaded" in stdout else stdout.find(" loaded")
        assert error_pos < loaded_heading_pos  # Error states shown first


class TestSystemVersion:
    """Test system version command."""

    def test_version(self) -> None:
        """Test version command."""
        result = runner.invoke(app, ["system", "version"])
        assert result.exit_code == 0
        assert "version" in result.stdout.lower()
