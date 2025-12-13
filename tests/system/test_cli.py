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
                host="10.0.20.35",
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
                host="10.0.20.35",
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
                host="10.0.20.35",
            )
        )

        result = runner.invoke(app, ["system", "info", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["data"]["version"] == "2025.12.1"


class TestSystemVersion:
    """Test system version command."""

    def test_version(self) -> None:
        """Test version command."""
        result = runner.invoke(app, ["system", "version"])
        assert result.exit_code == 0
        assert "version" in result.stdout.lower()
