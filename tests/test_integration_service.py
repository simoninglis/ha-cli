"""Integration tests for service layer."""

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_automation.client import HAClient
from ha_automation.exceptions import AutomationNotFoundError, ValidationError
from ha_automation.models import Automation
from ha_automation.service import AutomationCRUD, AutomationWS


# Sample automation YAML for testing
SAMPLE_AUTOMATION_YAML = """
alias: Test Automation
description: A test automation
trigger:
  - platform: time
    at: "10:00:00"
action:
  - service: light.turn_on
    target:
      entity_id: light.living_room
mode: single
"""


class TestAutomationCRUDIntegration:
    """Integration tests for AutomationCRUD service."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock HAClient."""
        return AsyncMock(spec=HAClient)
    
    @pytest.fixture
    def crud_service(self, mock_client):
        """Create AutomationCRUD service with mock client."""
        return AutomationCRUD(mock_client)
    
    @pytest.mark.asyncio
    async def test_list_automations_json_output(self, crud_service, mock_client):
        """Test list automations with JSON output (uses WebSocket)."""
        # WebSocket returns entity states format
        mock_states = [
            {"entity_id": "automation.test1", "state": "on", "attributes": {"friendly_name": "Test 1", "mode": "single"}},
            {"entity_id": "automation.test2", "state": "on", "attributes": {"friendly_name": "Test 2", "mode": "single"}}
        ]
        mock_client.get_automation_states.return_value = mock_states

        result = await crud_service.list_automations(json_output=True)

        assert len(result) == 2
        mock_client.get_automation_states.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_automations_object_output(self, crud_service, mock_client):
        """Test list automations with Automation objects (uses WebSocket)."""
        # WebSocket returns entity states format
        mock_states = [
            {"entity_id": "automation.test1", "state": "on", "attributes": {"friendly_name": "Test 1", "mode": "single"}},
            {"entity_id": "automation.test2", "state": "on", "attributes": {"friendly_name": "Test 2", "mode": "restart"}}
        ]
        mock_client.get_automation_states.return_value = mock_states

        result = await crud_service.list_automations(json_output=False)

        assert len(result) == 2
        assert all(isinstance(item, Automation) for item in result)
        assert result[0].id == "test1"
        assert result[0].alias == "Test 1"
        assert result[1].id == "test2"
        assert result[1].alias == "Test 2"
    
    @pytest.mark.asyncio
    async def test_get_automation_success(self, crud_service, mock_client):
        """Test successful get automation."""
        automation_data = {
            "id": "test1",
            "alias": "Test Automation",
            "trigger": [{"platform": "time", "at": "10:00"}],
            "action": [{"service": "light.turn_on"}],
            "mode": "single"
        }
        mock_client.get_automation.return_value = automation_data
        
        result = await crud_service.get_automation("test1")
        
        assert isinstance(result, Automation)
        assert result.id == "test1"
        assert result.alias == "Test Automation"
        mock_client.get_automation.assert_called_once_with("test1")
    
    @pytest.mark.asyncio
    async def test_get_automation_not_found(self, crud_service, mock_client):
        """Test get automation when not found."""
        mock_client.get_automation.side_effect = Exception("404 Not Found")
        
        with pytest.raises(AutomationNotFoundError):
            await crud_service.get_automation("nonexistent")
    
    @pytest.mark.asyncio
    async def test_create_automation_rest_api_unavailable(self, crud_service, mock_client):
        """Test create automation fails gracefully when REST API unavailable."""
        mock_client.probe_automation_rest_api.return_value = False

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(SAMPLE_AUTOMATION_YAML)
            f.flush()

            with pytest.raises(ValidationError, match="REST API not available"):
                await crud_service.create_automation(f.name)

    @pytest.mark.asyncio
    async def test_create_automation_success(self, crud_service, mock_client):
        """Test create automation with REST API available."""
        mock_client.probe_automation_rest_api.return_value = True
        mock_client.create_automation_rest.return_value = "1234567890123"
        mock_client.reload_automations.return_value = None

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(SAMPLE_AUTOMATION_YAML)
            f.flush()

            result = await crud_service.create_automation(f.name)

            assert result == "1234567890123"
            mock_client.create_automation_rest.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_automation_dry_run(self, crud_service, mock_client):
        """Test create automation dry run mode."""
        mock_client.probe_automation_rest_api.return_value = True

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(SAMPLE_AUTOMATION_YAML)
            f.flush()

            result = await crud_service.create_automation(f.name, dry_run=True)

            assert result == "DRY_RUN"
            mock_client.create_automation_rest.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_automation_file_not_found(self, crud_service, mock_client):
        """Test create automation with non-existent file."""
        mock_client.probe_automation_rest_api.return_value = True

        with pytest.raises(ValidationError, match="File not found"):
            await crud_service.create_automation("/nonexistent/file.yaml")

    @pytest.mark.asyncio
    async def test_create_automation_invalid_config(self, crud_service, mock_client):
        """Test create automation with invalid config (no trigger/action)."""
        mock_client.probe_automation_rest_api.return_value = True

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("alias: Invalid Automation\nmode: single\n")
            f.flush()

            with pytest.raises(ValidationError, match="must have 'trigger'"):
                await crud_service.create_automation(f.name)

    @pytest.mark.asyncio
    async def test_update_automation_rest_api_unavailable(self, crud_service, mock_client):
        """Test update automation fails gracefully when REST API unavailable."""
        mock_client.probe_automation_rest_api.return_value = False

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(SAMPLE_AUTOMATION_YAML)
            f.flush()

            with pytest.raises(ValidationError, match="REST API not available"):
                await crud_service.update_automation("test_automation", f.name)

    @pytest.mark.asyncio
    async def test_update_automation_success_with_entity_id(self, crud_service, mock_client):
        """Test update automation with entity ID (resolved to numeric ID)."""
        mock_client.probe_automation_rest_api.return_value = True
        mock_client.get_automation_numeric_id.return_value = "1234567890123"
        mock_client.update_automation_rest.return_value = None
        mock_client.reload_automations.return_value = None

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(SAMPLE_AUTOMATION_YAML)
            f.flush()

            await crud_service.update_automation("test_automation", f.name)

            mock_client.get_automation_numeric_id.assert_called_once_with("test_automation")
            mock_client.update_automation_rest.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_automation_success_with_numeric_id(self, crud_service, mock_client):
        """Test update automation with numeric ID (no resolution needed)."""
        mock_client.probe_automation_rest_api.return_value = True
        mock_client.update_automation_rest.return_value = None
        mock_client.reload_automations.return_value = None

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(SAMPLE_AUTOMATION_YAML)
            f.flush()

            await crud_service.update_automation("1234567890123", f.name)

            mock_client.get_automation_numeric_id.assert_not_called()
            mock_client.update_automation_rest.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_automation_not_found(self, crud_service, mock_client):
        """Test update automation when automation not found."""
        mock_client.probe_automation_rest_api.return_value = True
        mock_client.get_automation_numeric_id.return_value = None

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(SAMPLE_AUTOMATION_YAML)
            f.flush()

            with pytest.raises(AutomationNotFoundError):
                await crud_service.update_automation("nonexistent", f.name)

    @pytest.mark.asyncio
    async def test_delete_automation_rest_api_unavailable(self, crud_service, mock_client):
        """Test delete automation fails gracefully when REST API unavailable."""
        mock_client.probe_automation_rest_api.return_value = False

        with pytest.raises(ValidationError, match="REST API not available"):
            await crud_service.delete_automation("test_automation")

    @pytest.mark.asyncio
    async def test_delete_automation_success(self, crud_service, mock_client):
        """Test delete automation with REST API available."""
        mock_client.probe_automation_rest_api.return_value = True
        mock_client.get_automation_numeric_id.return_value = "1234567890123"
        mock_client.delete_automation_rest.return_value = None
        mock_client.reload_automations.return_value = None

        await crud_service.delete_automation("test_automation")

        mock_client.delete_automation_rest.assert_called_once_with("1234567890123")

    @pytest.mark.asyncio
    async def test_delete_automation_dry_run(self, crud_service, mock_client):
        """Test delete automation dry run mode."""
        mock_client.probe_automation_rest_api.return_value = True
        mock_client.get_automation_numeric_id.return_value = "1234567890123"

        await crud_service.delete_automation("test_automation", dry_run=True)

        mock_client.delete_automation_rest.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_automation_not_found(self, crud_service, mock_client):
        """Test delete automation when automation not found."""
        mock_client.probe_automation_rest_api.return_value = True
        mock_client.get_automation_numeric_id.return_value = None

        with pytest.raises(AutomationNotFoundError):
            await crud_service.delete_automation("nonexistent")


class TestAutomationWSIntegration:
    """Integration tests for AutomationWS service."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock HAClient."""
        return AsyncMock(spec=HAClient)
    
    @pytest.fixture
    def ws_service(self, mock_client):
        """Create AutomationWS service with mock client."""
        return AutomationWS(mock_client)
    
    @pytest.mark.asyncio
    async def test_enable_automation(self, ws_service, mock_client):
        """Test enable automation via WebSocket."""
        await ws_service.enable_automation("test_automation")
        
        mock_client.enable_automation.assert_called_once_with("test_automation")
    
    @pytest.mark.asyncio
    async def test_disable_automation(self, ws_service, mock_client):
        """Test disable automation via WebSocket."""
        await ws_service.disable_automation("test_automation") 
        
        mock_client.disable_automation.assert_called_once_with("test_automation")
    
    @pytest.mark.asyncio
    async def test_reload_automations(self, ws_service, mock_client):
        """Test reload all automations via WebSocket."""
        await ws_service.reload_automations()
        
        mock_client.reload_automations.assert_called_once()


class TestServiceIntegrationWorkflow:
    """Test complete workflows using both services."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock HAClient."""
        return AsyncMock(spec=HAClient)
    
    @pytest.fixture
    def crud_service(self, mock_client):
        """Create AutomationCRUD service."""
        return AutomationCRUD(mock_client)
    
    @pytest.fixture
    def ws_service(self, mock_client):
        """Create AutomationWS service."""
        return AutomationWS(mock_client)
    
    @pytest.mark.asyncio
    async def test_automation_lifecycle_read_only(self, crud_service, ws_service, mock_client):
        """Test automation lifecycle with read-only operations (WebSocket-based)."""
        automation_id = "lifecycle_test"

        # Read automation
        mock_client.get_automation.return_value = {
            "id": automation_id,
            "alias": "Lifecycle Test",
            "trigger": [{"platform": "time"}],
            "action": [{"service": "light.turn_on"}],
            "mode": "single"
        }
        automation = await crud_service.get_automation(automation_id)
        assert automation.alias == "Lifecycle Test"

        # Enable automation
        await ws_service.enable_automation(automation_id)
        mock_client.enable_automation.assert_called_with(automation_id)

        # Disable automation
        await ws_service.disable_automation(automation_id)
        mock_client.disable_automation.assert_called_with(automation_id)

        # Reload automations
        await ws_service.reload_automations()
        mock_client.reload_automations.assert_called()

    @pytest.mark.asyncio
    async def test_error_handling_workflow(self, crud_service, ws_service, mock_client):
        """Test error handling in various workflow scenarios."""

        # Test enable with client error
        mock_client.enable_automation.side_effect = Exception("WebSocket Error")

        with pytest.raises(Exception, match="WebSocket Error"):
            await ws_service.enable_automation("test_automation")

        # Test get automation with not found error
        mock_client.get_automation.side_effect = Exception("not_found")

        with pytest.raises(AutomationNotFoundError):
            await crud_service.get_automation("nonexistent")