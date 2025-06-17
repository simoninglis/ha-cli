"""Tests for UIAutomationManager."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_automation.exceptions import NotFoundError, ValidationError
from ha_automation.models import Automation
from ha_automation.storage.ui_automation_manager import UIAutomationManager


@pytest.fixture
def mock_client():
    """Create a mock HAClient."""
    client = MagicMock()
    client._request = AsyncMock()
    client.get_automation_config = AsyncMock()
    return client


@pytest.fixture
def ui_manager(mock_client):
    """Create a UIAutomationManager with mock client."""
    return UIAutomationManager(mock_client)


@pytest.fixture
def ui_automation():
    """Create a sample UI automation."""
    return Automation(
        id="1234567890abcdef1234567890abcdef",
        alias="Test UI Automation",
        trigger=[{"platform": "state", "entity_id": "sensor.test"}],
        action=[{"service": "light.turn_on", "entity_id": "light.test"}],
        mode="single",
    )


class TestUIAutomationManager:
    """Test UI automation management."""
    
    @pytest.mark.asyncio
    async def test_create_with_ui_id(self, ui_manager, mock_client, ui_automation):
        """Test creating automation with UI ID."""
        await ui_manager.create(ui_automation)
        
        # Verify REST API call
        mock_client._request.assert_called_once_with(
            method="POST",
            endpoint="/api/config/automation/config/1234567890abcdef1234567890abcdef",
            json_data={
                "id": "1234567890abcdef1234567890abcdef",
                "alias": "Test UI Automation",
                "triggers": [{"platform": "state", "entity_id": "sensor.test"}],
                "actions": [{"service": "light.turn_on", "entity_id": "light.test"}],
                "mode": "single",
            },
        )
    
    @pytest.mark.asyncio
    async def test_create_without_id(self, ui_manager, mock_client):
        """Test creating automation without ID (generates UI ID)."""
        automation = Automation(
            alias="No ID Automation",
            trigger=[{"platform": "state"}],
            action=[{"service": "test"}],
        )
        
        result = await ui_manager.create(automation)
        
        # Should generate UI ID
        assert len(result) == 32
        assert all(c in "0123456789abcdef" for c in result)
        
        # Verify API was called with generated ID
        assert mock_client._request.called
        call_args = mock_client._request.call_args
        assert call_args[1]["endpoint"].startswith("/api/config/automation/config/")
    
    @pytest.mark.asyncio
    async def test_create_with_invalid_id(self, ui_manager):
        """Test creating automation with non-UI ID."""
        automation = Automation(
            id="my_custom_id",
            alias="Invalid ID",
            trigger=[],
            action=[],
        )
        
        with pytest.raises(ValidationError, match="32-character hex IDs"):
            await ui_manager.create(automation)
    
    @pytest.mark.asyncio
    async def test_update(self, ui_manager, mock_client, ui_automation):
        """Test updating UI automation."""
        await ui_manager.update(ui_automation)
        
        # Verify REST API call (same endpoint as create)
        mock_client._request.assert_called_once_with(
            method="POST",
            endpoint="/api/config/automation/config/1234567890abcdef1234567890abcdef",
            json_data={
                "id": "1234567890abcdef1234567890abcdef",
                "alias": "Test UI Automation",
                "triggers": [{"platform": "state", "entity_id": "sensor.test"}],
                "actions": [{"service": "light.turn_on", "entity_id": "light.test"}],
                "mode": "single",
            },
        )
    
    @pytest.mark.asyncio
    async def test_update_without_id(self, ui_manager):
        """Test updating automation without ID."""
        automation = Automation(
            alias="No ID",
            trigger=[],
            action=[],
        )
        
        with pytest.raises(ValidationError, match="ID is required"):
            await ui_manager.update(automation)
    
    @pytest.mark.asyncio
    async def test_update_with_invalid_id(self, ui_manager):
        """Test updating automation with non-UI ID."""
        automation = Automation(
            id="not_ui_id",
            alias="Invalid",
            trigger=[],
            action=[],
        )
        
        with pytest.raises(ValidationError, match="Not a UI-style automation ID"):
            await ui_manager.update(automation)
    
    @pytest.mark.asyncio
    async def test_update_not_found(self, ui_manager, mock_client, ui_automation):
        """Test updating non-existent automation."""
        mock_client._request.side_effect = NotFoundError("Not found")
        
        with pytest.raises(NotFoundError):
            await ui_manager.update(ui_automation)
    
    @pytest.mark.asyncio
    async def test_delete(self, ui_manager, mock_client):
        """Test deleting UI automation."""
        automation_id = "1234567890abcdef1234567890abcdef"
        
        await ui_manager.delete(automation_id)
        
        mock_client._request.assert_called_once_with(
            method="DELETE",
            endpoint=f"/api/config/automation/config/{automation_id}",
        )
    
    @pytest.mark.asyncio
    async def test_delete_invalid_id(self, ui_manager):
        """Test deleting automation with non-UI ID."""
        with pytest.raises(ValidationError, match="Not a UI-style automation ID"):
            await ui_manager.delete("my_custom_id")
    
    @pytest.mark.asyncio
    async def test_delete_not_found(self, ui_manager, mock_client):
        """Test deleting non-existent automation."""
        mock_client._request.side_effect = NotFoundError("Not found")
        
        with pytest.raises(NotFoundError):
            await ui_manager.delete("1234567890abcdef1234567890abcdef")
    
    @pytest.mark.asyncio
    async def test_get_config(self, ui_manager, mock_client):
        """Test getting UI automation config."""
        automation_id = "1234567890abcdef1234567890abcdef"
        
        # Mock WebSocket response (singular format)
        mock_client.get_automation_config.return_value = {
            "id": automation_id,
            "alias": "Test",
            "trigger": [{"platform": "state"}],
            "action": [{"service": "test"}],
        }
        
        result = await ui_manager.get_config(automation_id)
        
        # Should return plural format
        assert "triggers" in result
        assert "actions" in result
        assert result["triggers"] == [{"platform": "state"}]
        assert result["actions"] == [{"service": "test"}]
    
    @pytest.mark.asyncio
    async def test_get_config_invalid_id(self, ui_manager):
        """Test getting config with non-UI ID."""
        with pytest.raises(ValidationError, match="Not a UI-style automation ID"):
            await ui_manager.get_config("not_ui_id")
    
    @pytest.mark.asyncio
    async def test_exists_true(self, ui_manager, mock_client):
        """Test checking if automation exists (true case)."""
        automation_id = "1234567890abcdef1234567890abcdef"
        
        mock_client.get_automation_config.return_value = {
            "id": automation_id,
            "alias": "Test",
            "trigger": [],
            "action": [],
        }
        
        result = await ui_manager.exists(automation_id)
        assert result is True
    
    @pytest.mark.asyncio
    async def test_exists_false(self, ui_manager, mock_client):
        """Test checking if automation exists (false case)."""
        automation_id = "1234567890abcdef1234567890abcdef"
        
        mock_client.get_automation_config.side_effect = NotFoundError("Not found")
        
        result = await ui_manager.exists(automation_id)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_fields_excluded_from_api(self, ui_manager, mock_client):
        """Test that certain fields are excluded from API calls."""
        automation = Automation(
            id="1234567890abcdef1234567890abcdef",
            alias="Test",
            trigger=[],
            action=[],
            last_triggered="2024-01-01T00:00:00",
            trace={"some": "data"},
        )
        
        await ui_manager.create(automation)
        
        call_data = mock_client._request.call_args[1]["json_data"]
        assert "last_triggered" not in call_data
        assert "trace" not in call_data