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
        """Test list automations with JSON output."""
        mock_data = [
            {"id": "test1", "alias": "Test 1", "trigger": [], "action": []},
            {"id": "test2", "alias": "Test 2", "trigger": [], "action": []}
        ]
        mock_client.list_automations.return_value = mock_data
        
        result = await crud_service.list_automations(json_output=True)
        
        assert result == mock_data
        mock_client.list_automations.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_list_automations_object_output(self, crud_service, mock_client):
        """Test list automations with Automation objects."""
        mock_data = [
            {
                "id": "test1", 
                "alias": "Test 1", 
                "trigger": [{"platform": "time"}], 
                "action": [{"service": "test"}],
                "mode": "single"
            },
            {
                "id": "test2", 
                "alias": "Test 2", 
                "trigger": [{"platform": "state"}], 
                "action": [{"service": "test2"}],
                "mode": "restart"
            }
        ]
        mock_client.list_automations.return_value = mock_data
        
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
    async def test_create_automation_from_yaml(self, crud_service, mock_client):
        """Test create automation from YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
alias: "Test Automation"
trigger:
  - platform: time
    at: "10:00:00"
action:
  - service: light.turn_on
    entity_id: light.test
mode: single
""")
            f.flush()
            
            mock_client.create_automation.return_value = {"id": "new_automation"}
            
            result = await crud_service.create_automation(f.name)
            
            assert result == "new_automation"
            mock_client.create_automation.assert_called_once()
            
            # Verify the automation data passed to client
            call_args = mock_client.create_automation.call_args[0][0]
            assert call_args["alias"] == "Test Automation"
            assert len(call_args["trigger"]) == 1
            assert len(call_args["action"]) == 1
        
        Path(f.name).unlink()  # Clean up
    
    @pytest.mark.asyncio
    async def test_create_automation_from_json(self, crud_service, mock_client):
        """Test create automation from JSON file."""
        automation_data = {
            "alias": "JSON Test Automation",
            "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
            "action": [{"service": "notify.test"}],
            "mode": "single"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(automation_data, f)
            f.flush()
            
            mock_client.create_automation.return_value = {"id": "json_automation"}
            
            result = await crud_service.create_automation(f.name)
            
            assert result == "json_automation"
            mock_client.create_automation.assert_called_once()
        
        Path(f.name).unlink()  # Clean up
    
    @pytest.mark.asyncio
    async def test_create_automation_file_not_found(self, crud_service, mock_client):
        """Test create automation with non-existent file."""
        with pytest.raises(ValidationError, match="File not found"):
            await crud_service.create_automation("/nonexistent/file.yaml")
    
    @pytest.mark.asyncio
    async def test_create_automation_invalid_extension(self, crud_service, mock_client):
        """Test create automation with invalid file extension."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("some content")
            f.flush()
            
            with pytest.raises(ValidationError, match="File must be YAML or JSON"):
                await crud_service.create_automation(f.name)
        
        Path(f.name).unlink()  # Clean up
    
    @pytest.mark.asyncio
    async def test_create_automation_validation_error(self, crud_service, mock_client):
        """Test create automation with invalid automation data."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
alias: "Invalid Automation"
# Missing required trigger and action
mode: single
""")
            f.flush()
            
            # Should raise ValidationError from Pydantic (wrapped in ValidationError)
            with pytest.raises(Exception):  # Pydantic ValidationError or our ValidationError
                await crud_service.create_automation(f.name)
        
        Path(f.name).unlink()  # Clean up
    
    @pytest.mark.asyncio
    async def test_update_automation_success(self, crud_service, mock_client):
        """Test successful update automation."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
alias: "Updated Automation"
trigger:
  - platform: time
    at: "11:00:00"
action:
  - service: light.turn_off
    entity_id: light.test
mode: restart
""")
            f.flush()
            
            await crud_service.update_automation("test_automation", f.name)
            
            mock_client.update_automation.assert_called_once()
            call_args = mock_client.update_automation.call_args[0]
            assert call_args[0] == "test_automation"  # automation_id
            
            automation_data = call_args[1]  # automation data dict
            assert automation_data["alias"] == "Updated Automation"
            assert automation_data["mode"] == "restart"
        
        Path(f.name).unlink()  # Clean up
    
    @pytest.mark.asyncio
    async def test_delete_automation(self, crud_service, mock_client):
        """Test delete automation."""
        await crud_service.delete_automation("test_automation")
        
        mock_client.delete_automation.assert_called_once_with("test_automation")
    
    def test_validate_automation_success(self, crud_service):
        """Test successful automation validation."""
        automation = Automation(
            alias="Valid Automation",
            trigger=[{"platform": "time", "at": "10:00"}],
            action=[{"service": "light.turn_on"}],
            mode="single"
        )
        
        # Should not raise any exception
        crud_service._validate_automation(automation)
    
    def test_validate_automation_no_alias(self, crud_service):
        """Test validation fails with no alias."""
        automation = Automation(
            alias="",  # Empty alias
            trigger=[{"platform": "time"}],
            action=[{"service": "test"}]
        )
        
        with pytest.raises(ValidationError, match="must have an alias"):
            crud_service._validate_automation(automation)
    
    def test_validate_automation_no_triggers(self, crud_service):
        """Test validation fails with no triggers."""
        automation = Automation(
            alias="Test",
            trigger=[],  # Empty triggers
            action=[{"service": "test"}]
        )
        
        with pytest.raises(ValidationError, match="must have at least one trigger"):
            crud_service._validate_automation(automation)
    
    def test_validate_automation_no_actions(self, crud_service):
        """Test validation fails with no actions."""
        automation = Automation(
            alias="Test",
            trigger=[{"platform": "time"}],
            action=[]  # Empty actions
        )
        
        with pytest.raises(ValidationError, match="must have at least one action"):
            crud_service._validate_automation(automation)
    
    def test_validate_automation_queued_mode_no_max(self, crud_service):
        """Test validation fails for queued mode without max."""
        automation = Automation(
            alias="Test",
            trigger=[{"platform": "time"}],
            action=[{"service": "test"}],
            mode="queued",
            max=None  # Required for queued mode
        )
        
        with pytest.raises(ValidationError, match="requires 'max' to be set"):
            crud_service._validate_automation(automation)
    
    def test_validate_automation_parallel_mode_no_max(self, crud_service):
        """Test validation fails for parallel mode without max."""
        automation = Automation(
            alias="Test",
            trigger=[{"platform": "time"}],
            action=[{"service": "test"}],
            mode="parallel",
            max=None  # Required for parallel mode
        )
        
        with pytest.raises(ValidationError, match="requires 'max' to be set"):
            crud_service._validate_automation(automation)


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
    async def test_complete_automation_lifecycle(self, crud_service, ws_service, mock_client):
        """Test complete automation lifecycle: create, enable, update, disable, delete."""
        
        # Create automation
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
alias: "Lifecycle Test"
trigger:
  - platform: time
    at: "10:00:00"
action:
  - service: light.turn_on
    entity_id: light.test
mode: single
""")
            f.flush()
            
            mock_client.create_automation.return_value = {"id": "lifecycle_test"}
            automation_id = await crud_service.create_automation(f.name)
            assert automation_id == "lifecycle_test"
        
        Path(f.name).unlink()
        
        # Enable automation
        await ws_service.enable_automation(automation_id)
        mock_client.enable_automation.assert_called_with(automation_id)
        
        # Update automation
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
alias: "Updated Lifecycle Test"
trigger:
  - platform: time
    at: "11:00:00"
action:
  - service: light.turn_off
    entity_id: light.test
mode: restart
""")
            f.flush()
            
            await crud_service.update_automation(automation_id, f.name)
            mock_client.update_automation.assert_called()
        
        Path(f.name).unlink()
        
        # Disable automation
        await ws_service.disable_automation(automation_id)
        mock_client.disable_automation.assert_called_with(automation_id)
        
        # Delete automation
        await crud_service.delete_automation(automation_id)
        mock_client.delete_automation.assert_called_with(automation_id)
        
        # Reload automations (called multiple times during the lifecycle)
        await ws_service.reload_automations()
        mock_client.reload_automations.assert_called()
    
    @pytest.mark.asyncio
    async def test_error_handling_workflow(self, crud_service, ws_service, mock_client):
        """Test error handling in various workflow scenarios."""
        
        # Test create with client error
        mock_client.create_automation.side_effect = Exception("API Error")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("""
alias: "Error Test"
trigger:
  - platform: time
    at: "10:00:00"
action:
  - service: light.turn_on
mode: single
""")
            f.flush()
            
            with pytest.raises(Exception, match="API Error"):
                await crud_service.create_automation(f.name)
        
        Path(f.name).unlink()
        
        # Test enable with client error
        mock_client.enable_automation.side_effect = Exception("WebSocket Error")
        
        with pytest.raises(Exception, match="WebSocket Error"):
            await ws_service.enable_automation("test_automation")
        
        # Test get automation with 404 error
        mock_client.get_automation.side_effect = Exception("404")
        
        with pytest.raises(AutomationNotFoundError):
            await crud_service.get_automation("nonexistent")