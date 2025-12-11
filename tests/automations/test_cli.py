"""Tests for automations CLI commands (ha_cli/domains/automations/cli.py)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from ha_cli.cli import app
from ha_cli.domains.automations.models import Automation

runner = CliRunner()


class TestAutomationsCLI:
    """Test automations CLI commands."""

    @patch("ha_cli.domains.automations.commands.list_cmd.get_client_config")
    @patch("ha_cli.domains.automations.commands.list_cmd.HAClient")
    @patch(
        "ha_cli.domains.automations.storage"
        ".unified_automation_service.UnifiedAutomationService"
    )
    def test_list_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test list command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_automations = [
            Automation(
                id="test_1",
                alias="Test Automation 1",
                trigger=[{"platform": "time"}],
                action=[{"service": "test"}],
                mode="single",
            ),
        ]

        mock_service.list_all = AsyncMock(return_value=test_automations)

        result = runner.invoke(app, ["automations", "list"])
        assert result.exit_code == 0
        assert "Test Automation 1" in result.stdout

    @patch("ha_cli.domains.automations.commands.list_cmd.get_client_config")
    @patch("ha_cli.domains.automations.commands.list_cmd.HAClient")
    @patch(
        "ha_cli.domains.automations.storage"
        ".unified_automation_service.UnifiedAutomationService"
    )
    def test_list_command_json(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test list command with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_automations = [
            Automation(
                id="test_1",
                alias="Test Automation 1",
                trigger=[{"platform": "time"}],
                action=[{"service": "test"}],
                mode="single",
            ),
        ]

        mock_service.list_all = AsyncMock(return_value=test_automations)

        result = runner.invoke(app, ["automations", "list", "--json"])
        assert result.exit_code == 0
        # Should be valid JSON
        output = json.loads(result.stdout)
        assert isinstance(output, list)

    @patch("ha_cli.domains.automations.commands.list_cmd.get_client_config")
    @patch("ha_cli.domains.automations.commands.list_cmd.HAClient")
    @patch(
        "ha_cli.domains.automations.storage"
        ".unified_automation_service.UnifiedAutomationService"
    )
    def test_list_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test list command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_automations = [
            Automation(
                id="test_1",
                alias="Test Automation 1",
                trigger=[{"platform": "time"}],
                action=[{"service": "test"}],
                mode="single",
            ),
        ]

        mock_service.list_all = AsyncMock(return_value=test_automations)

        result = runner.invoke(app, ["automations", "list", "--porcelain"])
        assert result.exit_code == 0
        # Should be valid JSON with porcelain envelope
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert "data" in output

    @patch("ha_cli.domains.automations.commands.read_cmd.get_client_config")
    @patch("ha_cli.domains.automations.commands.read_cmd.HAClient")
    @patch("ha_cli.domains.automations.commands.read_cmd.AutomationCRUD")
    def test_read_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test read command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_automation = Automation(
            id="test_1",
            alias="Test Automation 1",
            trigger=[{"platform": "time"}],
            action=[{"service": "test"}],
            mode="single",
            description="Test description",
        )

        mock_service.get_automation = AsyncMock(return_value=test_automation)

        result = runner.invoke(app, ["automations", "read", "test_1"])
        assert result.exit_code == 0
        assert "test_1" in result.stdout

    @patch("ha_cli.domains.automations.commands.control_cmd.get_client_config")
    @patch("ha_cli.domains.automations.commands.control_cmd.HAClient")
    def test_enable_command(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test enable command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.call_service = AsyncMock()

        result = runner.invoke(app, ["automations", "enable", "automation.test_1"])
        assert result.exit_code == 0
        assert "enabled" in result.stdout.lower() or "Enable" in result.stdout

    @patch("ha_cli.domains.automations.commands.control_cmd.get_client_config")
    @patch("ha_cli.domains.automations.commands.control_cmd.HAClient")
    def test_disable_command(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test disable command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.call_service = AsyncMock()

        result = runner.invoke(app, ["automations", "disable", "automation.test_1"])
        assert result.exit_code == 0
        assert "disabled" in result.stdout.lower() or "Disable" in result.stdout

    @patch("ha_cli.domains.automations.commands.control_cmd.get_client_config")
    @patch("ha_cli.domains.automations.commands.control_cmd.HAClient")
    def test_reload_command(
        self, mock_client_class: MagicMock, mock_config: MagicMock
    ) -> None:
        """Test reload command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.call_service = AsyncMock()

        result = runner.invoke(app, ["automations", "reload"])
        assert result.exit_code == 0
        assert "reload" in result.stdout.lower() or "Reload" in result.stdout

    def test_automations_help(self) -> None:
        """Test automations help shows all commands."""
        result = runner.invoke(app, ["automations", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "read" in result.stdout
        assert "enable" in result.stdout
        assert "disable" in result.stdout
        assert "reload" in result.stdout

    def test_automations_version(self) -> None:
        """Test automations version command."""
        result = runner.invoke(app, ["automations", "version"])
        assert result.exit_code == 0
        assert "version" in result.stdout.lower()
