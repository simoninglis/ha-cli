"""Tests for CLI commands."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_automation.cli import app
from ha_automation.exceptions import AutomationNotFoundError, HAAutomationError
from ha_automation.models import Automation

runner = CliRunner()


class TestCLI:
    """Test CLI commands."""
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    def test_version_command(self, mock_client_class, mock_config):
        """Test version command."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "ha-automation version" in result.stdout
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    @patch("ha_automation.storage.unified_automation_service.UnifiedAutomationService")
    def test_list_command(self, mock_service_class, mock_client_class, mock_config):
        """Test list command."""
        # Setup mocks
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        
        # Mock list_all to return test data
        test_automations = [
            Automation(
                id="test_1",
                alias="Test Automation 1",
                trigger=[{"platform": "time"}],
                action=[{"service": "test"}],
                mode="single",
            ),
            Automation(
                id="test_2",
                alias="Test Automation 2",
                trigger=[{"platform": "state"}],
                action=[{"service": "test"}],
                mode="restart",
            ),
        ]
        
        async def mock_list():
            return test_automations
        
        mock_service.list_all.side_effect = mock_list
        
        # Run command
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "Test Automation 1" in result.stdout
        assert "Test Automation 2" in result.stdout
        assert "Total: 2 automations" in result.stdout
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    @patch("ha_automation.storage.unified_automation_service.UnifiedAutomationService")
    def test_list_command_json(self, mock_service_class, mock_client_class, mock_config):
        """Test list command with JSON output."""
        # Setup mocks
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        
        # Mock list_all to return test data
        test_automations = [
            Automation(
                id="test_1",
                alias="Test 1",
                trigger=[{"platform": "time"}],
                action=[{"service": "test"}],
                mode="single",
            )
        ]
        
        async def mock_list():
            return test_automations
        
        mock_service.list_all.side_effect = mock_list
        
        # Run command
        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        
        # Should be valid JSON
        data = json.loads(result.stdout)
        assert isinstance(data, list)
        assert data[0]["id"] == "test_1"
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    @patch("ha_automation.cli.AutomationWS")
    def test_enable_command(self, mock_ws_class, mock_client_class, mock_config):
        """Test enable command."""
        # Setup mocks
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_ws = MagicMock()
        mock_ws_class.return_value = mock_ws
        
        async def mock_enable(automation_id):
            pass
        
        mock_ws.enable_automation.side_effect = mock_enable
        
        # Run command
        result = runner.invoke(app, ["enable", "test_automation"])
        assert result.exit_code == 0
        assert "Enabled automation test_automation" in result.stdout
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    @patch("ha_automation.cli.AutomationWS")
    def test_disable_command(self, mock_ws_class, mock_client_class, mock_config):
        """Test disable command."""
        # Setup mocks
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_ws = MagicMock()
        mock_ws_class.return_value = mock_ws
        
        async def mock_disable(automation_id):
            pass
        
        mock_ws.disable_automation.side_effect = mock_disable
        
        # Run command
        result = runner.invoke(app, ["disable", "test_automation"])
        assert result.exit_code == 0
        assert "Disabled automation test_automation" in result.stdout
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    @patch("ha_automation.cli.AutomationWS")
    def test_reload_command(self, mock_ws_class, mock_client_class, mock_config):
        """Test reload command."""
        # Setup mocks
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_ws = MagicMock()
        mock_ws_class.return_value = mock_ws
        
        async def mock_reload():
            pass
        
        mock_ws.reload_automations.side_effect = mock_reload
        
        # Run command
        result = runner.invoke(app, ["reload"])
        assert result.exit_code == 0
        assert "Reloaded all automations" in result.stdout
    
    def test_create_command_file_not_found(self):
        """Test create command with non-existent file."""
        result = runner.invoke(app, ["create", "nonexistent.yaml"])
        assert result.exit_code == 1
        assert "File not found" in result.stdout
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    @patch("ha_automation.storage.unified_automation_service.UnifiedAutomationService")
    def test_delete_command_with_confirmation(self, mock_service_class, mock_client_class, mock_config, tmp_path):
        """Test delete command with confirmation."""
        # Setup mocks
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        
        async def mock_delete(automation_id):
            pass
        
        mock_service.delete.side_effect = mock_delete
        
        # Run command with "n" for no
        result = runner.invoke(app, ["delete", "test_automation"], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.stdout
        
        # Run command with "y" for yes
        result = runner.invoke(app, ["delete", "test_automation"], input="y\n")
        assert result.exit_code == 0
        assert "Deleted automation test_automation" in result.stdout
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    @patch("ha_automation.storage.unified_automation_service.UnifiedAutomationService")
    def test_delete_command_force(self, mock_service_class, mock_client_class, mock_config):
        """Test delete command with force flag."""
        # Setup mocks
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        
        async def mock_delete(automation_id):
            pass
        
        mock_service.delete.side_effect = mock_delete
        
        # Run command
        result = runner.invoke(app, ["delete", "test_automation", "--force"])
        assert result.exit_code == 0
        assert "Deleted automation test_automation" in result.stdout
    
    @patch("ha_automation.cli.get_client_config")
    def test_error_handling(self, mock_config):
        """Test error handling shows proper exit codes."""
        # Simulate HA error
        mock_config.side_effect = HAAutomationError("Test error", {"detail": "test"})
        
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 3  # EXIT_HA_ERROR
        assert "Test error" in result.stdout
    
    @patch("ha_automation.storage.file_automation_manager.Path.home")
    def test_create_dry_run(self, mock_home, tmp_path):
        """Test create command with dry-run flag."""
        # Mock the home directory to use tmp_path
        mock_home.return_value = tmp_path
        
        # Create a test automation file
        automation_file = tmp_path / "test_automation.yaml"
        automation_file.write_text("""
alias: "Test Automation"
trigger:
  - platform: time
    at: "10:00:00"
action:
  - service: light.turn_on
    entity_id: light.test
mode: single
""")
        
        result = runner.invoke(app, ["create", str(automation_file), "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN:" in result.stdout
        assert "Would create automation:" in result.stdout
        assert "Test Automation" in result.stdout
        assert "Full YAML:" in result.stdout
    
    @patch("ha_automation.storage.file_automation_manager.Path.home")
    def test_delete_dry_run(self, mock_home, tmp_path):
        """Test delete command with dry-run flag."""
        # Mock the home directory to use tmp_path
        mock_home.return_value = tmp_path
        
        result = runner.invoke(app, ["delete", "test_automation", "--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN:" in result.stdout
        assert "Would delete automation test_automation" in result.stdout