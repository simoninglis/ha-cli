"""Tests for UnifiedAutomationService."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_automation.exceptions import NotFoundError, ValidationError
from ha_automation.models import Automation
from ha_automation.storage.unified_automation_service import UnifiedAutomationService


@pytest.fixture
def mock_client():
    """Create a mock HAClient."""
    client = MagicMock()
    client.get_automation_states = AsyncMock()
    client.get_automation_config = AsyncMock()
    return client


@pytest.fixture
def mock_ui_manager():
    """Create a mock UIAutomationManager."""
    manager = MagicMock()
    manager.create = AsyncMock()
    manager.update = AsyncMock()
    manager.delete = AsyncMock()
    manager.get_config = AsyncMock()
    manager.exists = AsyncMock()
    return manager


@pytest.fixture
def mock_file_manager():
    """Create a mock FileAutomationManager."""
    manager = MagicMock()
    manager.load_all = AsyncMock()
    manager.create = AsyncMock()
    manager.update = AsyncMock()
    manager.delete = AsyncMock()
    manager.get_by_id = AsyncMock()
    manager.exists = AsyncMock()
    return manager


@pytest.fixture
def unified_service(mock_client, mock_ui_manager, mock_file_manager):
    """Create UnifiedAutomationService with mocked managers."""
    service = UnifiedAutomationService(mock_client)
    service.ui_manager = mock_ui_manager
    service.file_manager = mock_file_manager
    return service


class TestUnifiedAutomationService:
    """Test unified automation service."""
    
    @pytest.mark.asyncio
    async def test_list_all(self, unified_service, mock_client, mock_file_manager):
        """Test listing all automations."""
        # Mock WebSocket response - returns entity states
        mock_client.get_automation_states.return_value = [
            {
                "entity_id": "automation.1234567890abcdef1234567890abcdef",
                "state": "on",
                "attributes": {
                    "friendly_name": "UI Automation",
                    "mode": "single",
                },
            },
            {
                "entity_id": "automation.file_automation_1",
                "state": "on",
                "attributes": {
                    "friendly_name": "File Automation 1",
                    "mode": "single",
                },
            },
        ]

        # Mock file manager response
        mock_file_manager.load_all.return_value = [
            Automation(
                id="file_automation_1",
                alias="File Automation 1",
                trigger=[],
                action=[],
            ),
            Automation(
                id="file_automation_2",
                alias="File Automation 2",
                trigger=[],
                action=[],
            ),
        ]

        result = await unified_service.list_all()

        # Should deduplicate and include all unique automations
        assert len(result) == 3
        ids = [a.id for a in result]
        assert "1234567890abcdef1234567890abcdef" in ids
        assert "file_automation_1" in ids
        assert "file_automation_2" in ids
    
    @pytest.mark.asyncio
    async def test_get_by_id_websocket(self, unified_service, mock_client):
        """Test getting automation via WebSocket."""
        mock_client.get_automation_config.return_value = {
            "id": "test_automation",
            "alias": "Test",
            "trigger": [{"platform": "state"}],
            "action": [{"service": "test"}],
        }
        
        result = await unified_service.get_by_id("test_automation")
        
        assert result.id == "test_automation"
        assert result.alias == "Test"
    
    @pytest.mark.asyncio
    async def test_get_by_id_file_fallback(self, unified_service, mock_client, mock_file_manager):
        """Test getting automation from file when WebSocket fails."""
        mock_client.get_automation_config.side_effect = NotFoundError("Not found")
        
        file_automation = Automation(
            id="file_only",
            alias="File Only",
            trigger=[],
            action=[],
        )
        mock_file_manager.get_by_id.return_value = file_automation
        
        result = await unified_service.get_by_id("file_only")
        
        assert result == file_automation
    
    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, unified_service, mock_client, mock_file_manager):
        """Test getting non-existent automation."""
        mock_client.get_automation_config.side_effect = NotFoundError("Not found")
        mock_file_manager.get_by_id.return_value = None
        
        with pytest.raises(NotFoundError):
            await unified_service.get_by_id("nonexistent")
    
    @pytest.mark.asyncio
    async def test_create_auto_ui(self, unified_service, mock_ui_manager):
        """Test auto-creating UI automation based on ID."""
        automation = Automation(
            id="1234567890abcdef1234567890abcdef",
            alias="Auto UI",
            trigger=[],
            action=[],
        )
        
        mock_ui_manager.create.return_value = automation.id
        
        result = await unified_service.create(automation, storage_type="auto")
        
        assert result == automation.id
        mock_ui_manager.create.assert_called_once_with(automation)
    
    @pytest.mark.asyncio
    async def test_create_auto_file(self, unified_service, mock_file_manager):
        """Test auto-creating file automation."""
        automation = Automation(
            id="my_automation",
            alias="Auto File",
            trigger=[],
            action=[],
        )
        
        mock_file_manager.create.return_value = automation.id
        
        result = await unified_service.create(automation, storage_type="auto")
        
        assert result == automation.id
        mock_file_manager.create.assert_called_once_with(automation)
    
    @pytest.mark.asyncio
    async def test_create_explicit_ui(self, unified_service, mock_ui_manager):
        """Test explicitly creating UI automation."""
        automation = Automation(
            alias="Explicit UI",
            trigger=[],
            action=[],
        )
        
        mock_ui_manager.create.return_value = "1234567890abcdef1234567890abcdef"
        
        result = await unified_service.create(automation, storage_type="ui")
        
        mock_ui_manager.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_explicit_file(self, unified_service, mock_file_manager):
        """Test explicitly creating file automation."""
        automation = Automation(
            alias="Explicit File",
            trigger=[],
            action=[],
        )
        
        mock_file_manager.create.return_value = "explicit_file_123"
        
        result = await unified_service.create(automation, storage_type="file")
        
        mock_file_manager.create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_ui_automation(self, unified_service, mock_ui_manager):
        """Test updating UI automation."""
        automation = Automation(
            id="1234567890abcdef1234567890abcdef",
            alias="Updated UI",
            trigger=[],
            action=[],
        )
        
        await unified_service.update(automation)
        
        mock_ui_manager.update.assert_called_once_with(automation)
    
    @pytest.mark.asyncio
    async def test_update_file_automation(self, unified_service, mock_file_manager):
        """Test updating file automation."""
        automation = Automation(
            id="file_automation",
            alias="Updated File",
            trigger=[],
            action=[],
        )
        
        await unified_service.update(automation)
        
        mock_file_manager.update.assert_called_once_with(automation)
    
    @pytest.mark.asyncio
    async def test_update_without_id(self, unified_service):
        """Test updating automation without ID."""
        automation = Automation(
            alias="No ID",
            trigger=[],
            action=[],
        )
        
        with pytest.raises(ValidationError, match="ID is required"):
            await unified_service.update(automation)
    
    @pytest.mark.asyncio
    async def test_delete_ui_automation(self, unified_service, mock_ui_manager):
        """Test deleting UI automation."""
        await unified_service.delete("1234567890abcdef1234567890abcdef")
        
        mock_ui_manager.delete.assert_called_once_with("1234567890abcdef1234567890abcdef")
    
    @pytest.mark.asyncio
    async def test_delete_file_automation(self, unified_service, mock_file_manager):
        """Test deleting file automation."""
        await unified_service.delete("file_automation")
        
        mock_file_manager.delete.assert_called_once_with("file_automation")
    
    @pytest.mark.asyncio
    async def test_delete_file_fallback_to_ui(self, unified_service, mock_file_manager, mock_ui_manager):
        """Test delete falls back to UI if not found in file."""
        mock_file_manager.delete.side_effect = NotFoundError("Not in file")
        
        await unified_service.delete("custom_id")
        
        mock_ui_manager.delete.assert_called_once_with("custom_id")
    
    @pytest.mark.asyncio
    async def test_migrate_file_to_ui(self, unified_service, mock_client, mock_ui_manager):
        """Test migrating file automation to UI storage."""
        # Mock getting the automation
        mock_client.get_automation_config.return_value = {
            "id": "file_automation",
            "alias": "To Be Migrated",
            "trigger": [{"platform": "state"}],
            "action": [{"service": "test"}],
        }
        
        # Mock creation returns new UI ID
        mock_ui_manager.create.return_value = "1234567890abcdef1234567890abcdef"
        
        new_id = await unified_service.migrate("file_automation", "ui")
        
        assert new_id == "1234567890abcdef1234567890abcdef"
        # Should have cleared the ID before creating
        created_automation = mock_ui_manager.create.call_args[0][0]
        assert created_automation.id is None
    
    @pytest.mark.asyncio
    async def test_migrate_ui_to_file(self, unified_service, mock_client, mock_file_manager):
        """Test migrating UI automation to file storage."""
        # Mock getting the automation
        mock_client.get_automation_config.return_value = {
            "id": "1234567890abcdef1234567890abcdef",
            "alias": "To File Storage",
            "triggers": [{"platform": "state"}],  # UI format
            "actions": [{"service": "test"}],
        }
        
        # Mock creation returns new file ID
        mock_file_manager.create.return_value = "to_file_storage_123"
        
        new_id = await unified_service.migrate("1234567890abcdef1234567890abcdef", "file")
        
        assert new_id == "to_file_storage_123"
        # Should have cleared the UI-style ID
        created_automation = mock_file_manager.create.call_args[0][0]
        assert created_automation.id is None
    
    @pytest.mark.asyncio
    async def test_migrate_same_storage(self, unified_service, mock_client):
        """Test migrating to same storage type."""
        mock_client.get_automation_config.return_value = {
            "id": "file_automation",
            "alias": "Already File",
            "trigger": [],
            "action": [],
        }
        
        result = await unified_service.migrate("file_automation", "file")
        
        # Should return same ID without changes
        assert result == "file_automation"
    
    @pytest.mark.asyncio
    async def test_analyze_storage(self, unified_service, mock_client, mock_file_manager):
        """Test analyzing storage distribution."""
        # Mock returns entity states (WebSocket format)
        mock_client.get_automation_states.return_value = [
            {"entity_id": "automation.1234567890abcdef1234567890abcdef", "state": "on", "attributes": {"friendly_name": "UI 1", "mode": "single"}},
            {"entity_id": "automation.abcdefabcdefabcdefabcdefabcdefab", "state": "on", "attributes": {"friendly_name": "UI 2", "mode": "single"}},
            {"entity_id": "automation.file_1", "state": "on", "attributes": {"friendly_name": "File 1", "mode": "single"}},
        ]

        mock_file_manager.load_all.return_value = []

        analysis = await unified_service.analyze_storage()

        assert analysis["total"] == 3
        assert analysis["ui_count"] == 2
        assert analysis["file_count"] == 1
        assert analysis["mixed_storage"] is True
    
    @pytest.mark.asyncio
    async def test_validate_all(self, unified_service, mock_client, mock_file_manager):
        """Test validating all automations."""
        # Mock returns entity states (WebSocket format)
        # Note: WebSocket only provides minimal info, triggers/actions are empty
        mock_client.get_automation_states.return_value = [
            {"entity_id": "automation.1234567890abcdef1234567890abcdef", "state": "on", "attributes": {"friendly_name": "Valid UI", "mode": "single"}},
            {"entity_id": "automation.file_automation", "state": "on", "attributes": {"friendly_name": "Valid File", "mode": "single"}},
            {"entity_id": "automation.ui_in_file", "state": "on", "attributes": {"friendly_name": "Misplaced", "mode": "single"}},
            {"entity_id": "automation.no_action", "state": "on", "attributes": {"friendly_name": "No Action", "mode": "single"}},
        ]

        mock_file_manager.load_all.return_value = []

        issues = await unified_service.validate_all()

        # All automations from WebSocket will have empty trigger/action (limitation of WebSocket list)
        # So all 4 should have validation issues
        assert len(issues) == 4