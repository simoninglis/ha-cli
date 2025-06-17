"""Integration tests for dashboard CLI commands."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_cli.common.exceptions import NotFoundError, ValidationError
from ha_cli.domains.dashboards import cli
from ha_cli.domains.dashboards.models import DashboardConfig, DashboardInfo


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Set up environment variables for testing."""
    monkeypatch.setenv("HA_URL", "http://localhost:8123")
    monkeypatch.setenv("HA_TOKEN", "test-token")


@pytest.fixture
def mock_config():
    """Mock config file."""
    return {
        "url": "http://localhost:8123",
        "token": "test-token",
    }


@pytest.fixture
def sample_dashboards():
    """Sample dashboard list."""
    return [
        DashboardInfo(
            id="default",
            url_path="",
            title="Default",
            mode="storage",
            require_admin=False,
            show_in_sidebar=True,
        ),
        DashboardInfo(
            id="mobile",
            url_path="mobile",
            title="Mobile Dashboard",
            icon="mdi:cellphone",
            mode="storage",
            require_admin=False,
            show_in_sidebar=True,
        ),
        DashboardInfo(
            id="admin",
            url_path="admin",
            title="Admin Panel",
            icon="mdi:shield",
            mode="yaml",
            require_admin=True,
            show_in_sidebar=False,
        ),
    ]


@pytest.fixture
def sample_dashboard_config():
    """Sample dashboard configuration."""
    return DashboardConfig(
        title="Test Dashboard",
        version=1,
        views=[]
    )


class TestDashboardCLI:
    """Test dashboard CLI commands."""
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_list_command(self, mock_service_class, mock_client_class, runner, sample_dashboards):
        """Test list dashboards command."""
        
        mock_service = AsyncMock()
        mock_service.list_dashboards.return_value = sample_dashboards
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["list"])
        
        assert result.exit_code == 0
        assert "Home Assistant Dashboards" in result.output
        assert "default" in result.output
        assert "Mobile Dashboard" in result.output
        assert "Admin Panel" in result.output
        assert "✓" in result.output  # Sidebar indicator
        assert "✗" in result.output  # Not in sidebar
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_list_command_json(self, mock_service_class, mock_client_class, runner, sample_dashboards):
        """Test list dashboards with JSON output."""
        
        mock_service = AsyncMock()
        mock_service.list_dashboards.return_value = sample_dashboards
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["list", "--json"])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 3
        assert data[0]["id"] == "default"
        assert data[1]["id"] == "mobile"
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_read_command(self, mock_service_class, mock_client_class, runner, sample_dashboard_config):
        """Test read dashboard command."""
        
        mock_service = AsyncMock()
        mock_service.get_dashboard.return_value = sample_dashboard_config
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["read", "mobile"])
        
        assert result.exit_code == 0
        assert "title: Test Dashboard" in result.output
        assert "version: 1" in result.output
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_read_command_json(self, mock_service_class, mock_client_class, runner, sample_dashboard_config):
        """Test read dashboard with JSON output."""
        
        mock_service = AsyncMock()
        mock_service.get_dashboard.return_value = sample_dashboard_config
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["read", "mobile", "--format", "json"])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["title"] == "Test Dashboard"
        assert data["version"] == 1
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_read_command_save_to_file(self, mock_service_class, mock_client_class, runner, sample_dashboard_config, tmp_path):
        """Test read dashboard and save to file."""
        
        mock_service = AsyncMock()
        mock_service.get_dashboard.return_value = sample_dashboard_config
        mock_service_class.return_value = mock_service
        
        output_file = tmp_path / "dashboard.yaml"
        
        result = runner.invoke(cli.app, ["read", "mobile", "--output", str(output_file)])
        
        assert result.exit_code == 0
        assert "Dashboard saved to" in result.output
        assert str(output_file) in result.output
        assert output_file.exists()
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_backup_command(self, mock_service_class, mock_client_class, runner):
        """Test backup dashboard command."""
        
        mock_service = AsyncMock()
        mock_service.backup_dashboard.return_value = "/path/to/backup.yaml"
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["backup", "mobile"])
        
        assert result.exit_code == 0
        assert "Dashboard backed up to: /path/to/backup.yaml" in result.output
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_backup_command_with_output(self, mock_service_class, mock_client_class, runner):
        """Test backup dashboard with custom output."""
        
        mock_service = AsyncMock()
        mock_service.backup_dashboard.return_value = "custom-backup.yaml"
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["backup", "mobile", "--output", "custom-backup.yaml"])
        
        assert result.exit_code == 0
        mock_service.backup_dashboard.assert_called_once_with(
            url_path="mobile",
            output_file="custom-backup.yaml",
            format="yaml"
        )
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_restore_command(self, mock_service_class, mock_client_class, runner):
        """Test restore dashboard command."""
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["restore", "backup.yaml"])
        
        assert result.exit_code == 0
        assert "Dashboard restored successfully" in result.output
        mock_service.restore_dashboard.assert_called_once_with(
            input_file="backup.yaml",
            url_path=None,
            validate_only=False
        )
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_restore_command_validate_only(self, mock_service_class, mock_client_class, runner):
        """Test restore dashboard validation only."""
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["restore", "backup.yaml", "--validate-only"])
        
        assert result.exit_code == 0
        assert "Dashboard configuration is valid" in result.output
        mock_service.restore_dashboard.assert_called_once_with(
            input_file="backup.yaml",
            url_path=None,
            validate_only=True
        )
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_entities_command(self, mock_service_class, mock_client_class, runner):
        """Test list entities command."""
        
        mock_service = AsyncMock()
        mock_service.get_entity_references.return_value = [
            "light.living_room",
            "light.bedroom",
            "sensor.temperature",
            "switch.fan",
            "climate.thermostat",
        ]
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["entities"])
        
        assert result.exit_code == 0
        assert "Found 5 unique entities" in result.output
        assert "light:" in result.output
        assert "light.living_room" in result.output
        assert "sensor:" in result.output
        assert "sensor.temperature" in result.output
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_entities_command_json(self, mock_service_class, mock_client_class, runner):
        """Test list entities with JSON output."""
        
        mock_service = AsyncMock()
        mock_service.get_entity_references.return_value = ["light.living_room", "sensor.temperature"]
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["entities", "--json"])
        
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert "light.living_room" in data
        assert "sensor.temperature" in data
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_create_command(self, mock_service_class, mock_client_class, runner):
        """Test create dashboard command."""
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["create", "test-dash", "test", "Test Dashboard"])
        
        assert result.exit_code == 0
        assert "Dashboard 'test-dash' created successfully" in result.output
        assert "URL: /lovelace/test" in result.output
        
        mock_service.create_dashboard.assert_called_once_with(
            dashboard_id="test-dash",
            url_path="test",
            title="Test Dashboard",
            icon=None,
            show_in_sidebar=True,
            require_admin=False,
        )
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_create_command_with_options(self, mock_service_class, mock_client_class, runner):
        """Test create dashboard with all options."""
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, [
            "create", "admin-dash", "admin", "Admin Panel",
            "--icon", "mdi:shield",
            "--no-sidebar",
            "--require-admin"
        ])
        
        assert result.exit_code == 0
        
        mock_service.create_dashboard.assert_called_once_with(
            dashboard_id="admin-dash",
            url_path="admin",
            title="Admin Panel",
            icon="mdi:shield",
            show_in_sidebar=False,
            require_admin=True,
        )
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_delete_command_with_confirmation(self, mock_service_class, mock_client_class, runner):
        """Test delete dashboard with confirmation."""
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        # Simulate user confirming
        result = runner.invoke(cli.app, ["delete", "test-dash"], input="y\n")
        
        assert result.exit_code == 0
        assert "Dashboard 'test-dash' deleted successfully" in result.output
        mock_service.delete_dashboard.assert_called_once_with("test-dash")
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_delete_command_cancelled(self, mock_service_class, mock_client_class, runner):
        """Test delete dashboard cancelled."""
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        # Simulate user cancelling
        result = runner.invoke(cli.app, ["delete", "test-dash"], input="n\n")
        
        assert result.exit_code == 0
        assert "Deletion cancelled" in result.output
        mock_service.delete_dashboard.assert_not_called()
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_delete_command_force(self, mock_service_class, mock_client_class, runner):
        """Test delete dashboard with force flag."""
        
        mock_service = AsyncMock()
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["delete", "test-dash", "--force"])
        
        assert result.exit_code == 0
        assert "Dashboard 'test-dash' deleted successfully" in result.output
        mock_service.delete_dashboard.assert_called_once_with("test-dash")
    
    def test_version_command(self, runner):
        """Test version command."""
        result = runner.invoke(cli.app, ["version"])
        
        assert result.exit_code == 0
        assert "ha-cli dashboards version" in result.output
    
    @patch("ha_cli.domains.dashboards.cli.HAClient")
    @patch("ha_cli.domains.dashboards.cli.DashboardService")
    def test_error_handling(self, mock_service_class, mock_client_class, runner):
        """Test error handling."""
        
        mock_service = AsyncMock()
        mock_service.get_dashboard.side_effect = NotFoundError("Dashboard not found: mobile")
        mock_service_class.return_value = mock_service
        
        result = runner.invoke(cli.app, ["read", "mobile"])
        
        assert result.exit_code == 3  # EXIT_HA_ERROR
        assert "Dashboard not found: mobile" in result.output