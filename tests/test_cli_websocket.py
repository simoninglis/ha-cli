"""Tests for WebSocket CLI commands."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_automation.cli import app
from ha_automation.monitor import AutomationExecutionEvent, AutomationMonitor
from ha_automation.trigger_tester import TriggerEvent, TriggerTestResult, TriggerTester

runner = CliRunner()


class TestMonitorCommand:
    """Test monitor command."""
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    def test_monitor_one_time(self, mock_client_class, mock_get_config):
        """Test monitor command in one-time mode."""
        # Setup mocks
        mock_get_config.return_value = ("http://test:8123", "test-token")
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock monitor
        mock_monitor = MagicMock(spec=AutomationMonitor)
        mock_monitor.start_monitoring = AsyncMock()
        mock_monitor.stop_monitoring = AsyncMock()
        mock_monitor.get_all_states.return_value = {
            "test1": MagicMock(is_enabled=True),
            "test2": MagicMock(is_enabled=False),
        }
        mock_monitor.get_all_metrics.return_value = {
            "test1": {
                "last_execution": "2025-06-14T10:00:00",
                "executions_per_hour": 2.5,
            },
            "test2": {
                "last_execution": "Never",
                "executions_per_hour": 0.0,
            },
        }
        
        with patch("ha_automation.monitor.AutomationMonitor", return_value=mock_monitor):
            result = runner.invoke(app, ["monitor"])
            
            assert result.exit_code == 0
            assert "Started monitoring automations" in result.stdout
            assert "Automation Status" in result.stdout
            assert "test1" in result.stdout
            assert "test2" in result.stdout


class TestTestTriggerCommand:
    """Test test-trigger command."""
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    def test_test_trigger_batch_mode(self, mock_client_class, mock_get_config, tmp_path):
        """Test test-trigger command in batch mode."""
        # Create trigger file
        trigger_file = tmp_path / "trigger.yaml"
        trigger_file.write_text("platform: time\nat: '10:00:00'")
        
        # Setup mocks
        mock_get_config.return_value = ("http://test:8123", "test-token")
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock tester
        mock_tester = MagicMock(spec=TriggerTester)
        mock_tester.validate_trigger_config.return_value = []  # No errors
        mock_tester.test_trigger = AsyncMock()
        
        # Mock successful result
        mock_result = TriggerTestResult(
            trigger_config={"platform": "time", "at": "10:00:00"},
            start_time=datetime.now(),
            end_time=datetime.now(),
        )
        mock_result.events_received = [
            TriggerEvent(
                timestamp=datetime.now(),
                trigger_data={},
                variables={
                    "trigger": {
                        "platform": "time",
                        "at": "10:00:00",
                        "now": "2025-06-14T10:00:00",
                    }
                },
            )
        ]
        mock_tester.test_trigger = AsyncMock(return_value=mock_result)
        
        with patch("ha_automation.trigger_tester.TriggerTester", return_value=mock_tester):
            result = runner.invoke(app, ["test-trigger", str(trigger_file)])
            
            assert result.exit_code == 0
            assert "Testing trigger: time" in result.stdout
            assert "Test successful!" in result.stdout
            assert "Collected 1 events" in result.stdout
    
    def test_test_trigger_file_not_found(self):
        """Test test-trigger command with missing file."""
        result = runner.invoke(app, ["test-trigger", "nonexistent.yaml"])
        
        assert result.exit_code != 0
        assert "File not found" in result.stdout


class TestEventsCommand:
    """Test events command."""
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    def test_events_automations_only(self, mock_client_class, mock_get_config):
        """Test events command with automations-only filter."""
        # Setup mocks
        mock_get_config.return_value = ("http://test:8123", "test-token")
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        
        # Mock event stream (empty to avoid infinite loop in test)
        async def mock_events():
            # Yield nothing to exit immediately
            return
            yield  # Never reached
        
        mock_client.subscribe_automation_events.return_value = mock_events()
        
        # Use patch to simulate KeyboardInterrupt after setup
        with patch("asyncio.Event.wait", side_effect=KeyboardInterrupt):
            result = runner.invoke(app, ["events", "--automations-only"])
            
            # Should handle gracefully
            assert "Connected to Home Assistant" in result.stdout


class TestControlCommand:
    """Test control command."""
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    def test_control_enable(self, mock_client_class, mock_get_config):
        """Test control command to enable automations."""
        # Setup mocks
        mock_get_config.return_value = ("http://test:8123", "test-token")
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.call_automation_service = AsyncMock()
        
        result = runner.invoke(app, ["control", "enable", "test1,test2"])
        
        assert result.exit_code == 0
        assert "Successfully enabled 2 automation(s)" in result.stdout
        assert "automation.test1" in result.stdout
        assert "automation.test2" in result.stdout
        
        # Verify service call
        mock_client.call_automation_service.assert_called_once_with(
            "turn_on",
            ["automation.test1", "automation.test2"]
        )
    
    @patch("ha_automation.cli.get_client_config")
    @patch("ha_automation.cli.HAClient")
    def test_control_trigger(self, mock_client_class, mock_get_config):
        """Test control command to trigger automation."""
        # Setup mocks
        mock_get_config.return_value = ("http://test:8123", "test-token")
        mock_client = MagicMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.call_automation_service = AsyncMock()
        
        # Test with full entity ID
        result = runner.invoke(app, ["control", "trigger", "automation.test"])
        
        assert result.exit_code == 0
        assert "Successfully triggered 1 automation(s)" in result.stdout
        
        # Verify service call
        mock_client.call_automation_service.assert_called_once_with(
            "trigger",
            ["automation.test"]
        )
    
    def test_control_invalid_action(self):
        """Test control command with invalid action."""
        result = runner.invoke(app, ["control", "invalid", "test"])
        
        assert result.exit_code != 0
        assert "Invalid action 'invalid'" in result.stdout
        assert "enable, disable, trigger" in result.stdout  # Just check for part of the message