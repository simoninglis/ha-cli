"""Tests for FileAutomationManager."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import ruamel.yaml

from ha_automation.exceptions import NotFoundError, ValidationError
from ha_automation.models import Automation
from ha_automation.storage.file_automation_manager import FileAutomationManager


@pytest.fixture
def mock_client():
    """Create a mock HAClient."""
    client = MagicMock()
    client.call_automation_service = AsyncMock()
    return client


@pytest.fixture
def temp_automations_file():
    """Create a temporary automations.yaml file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml = ruamel.yaml.YAML()
        yaml.dump([
            {
                "id": "existing_automation",
                "alias": "Existing Automation",
                "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
                "action": [{"service": "light.turn_on", "entity_id": "light.test"}],
            },
            {
                "id": "another_automation",
                "alias": "Another Automation",
                "trigger": [{"platform": "time", "at": "10:00:00"}],
                "action": [{"service": "notify.notify", "message": "Hello"}],
            },
        ], f)
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    temp_path.unlink(missing_ok=True)
    # Also clean up any backup files
    for backup in temp_path.parent.glob(f"{temp_path.stem}.*.backup"):
        backup.unlink(missing_ok=True)


@pytest.fixture
def file_manager(mock_client, temp_automations_file):
    """Create a FileAutomationManager with temp file."""
    return FileAutomationManager(mock_client, temp_automations_file)


@pytest.fixture
def file_automation():
    """Create a sample file-based automation."""
    return Automation(
        id="test_automation_123",
        alias="Test File Automation",
        trigger=[{"platform": "state", "entity_id": "sensor.test"}],
        action=[{"service": "light.turn_off", "entity_id": "light.test"}],
        mode="restart",
    )


class TestFileAutomationManager:
    """Test file-based automation management."""
    
    @pytest.mark.asyncio
    async def test_load_all(self, file_manager):
        """Test loading all automations from file."""
        automations = await file_manager.load_all()
        
        assert len(automations) == 2
        assert automations[0].id == "existing_automation"
        assert automations[0].alias == "Existing Automation"
        assert automations[1].id == "another_automation"
        assert automations[1].alias == "Another Automation"
    
    @pytest.mark.asyncio
    async def test_load_all_empty_file(self, mock_client):
        """Test loading from empty file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml') as f:
            f.write("")
            f.flush()
            
            manager = FileAutomationManager(mock_client, Path(f.name))
            automations = await manager.load_all()
            
            assert automations == []
    
    @pytest.mark.asyncio
    async def test_load_all_nonexistent_file(self, mock_client):
        """Test loading from non-existent file."""
        manager = FileAutomationManager(mock_client, Path("/nonexistent/file.yaml"))
        automations = await manager.load_all()
        
        assert automations == []
    
    @pytest.mark.asyncio
    async def test_save_all(self, file_manager, mock_client):
        """Test saving automations to file."""
        automations = [
            Automation(
                id="new_automation",
                alias="New Automation",
                trigger=[{"platform": "sun", "event": "sunset"}],
                action=[{"service": "scene.turn_on", "entity_id": "scene.evening"}],
            ),
        ]
        
        await file_manager.save_all(automations)
        
        # Verify file contents
        yaml = ruamel.yaml.YAML()
        with open(file_manager.automations_file, 'r') as f:
            data = yaml.load(f)
        
        assert len(data) == 1
        assert data[0]["id"] == "new_automation"
        assert data[0]["alias"] == "New Automation"
        
        # Verify HA reload was triggered
        mock_client.call_automation_service.assert_called_once_with("reload", [])
    
    @pytest.mark.asyncio
    async def test_create_with_custom_id(self, file_manager, file_automation):
        """Test creating automation with custom ID."""
        result_id = await file_manager.create(file_automation)
        
        assert result_id == "test_automation_123"
        
        # Verify it was added to file
        automations = await file_manager.load_all()
        assert len(automations) == 3
        assert any(a.id == "test_automation_123" for a in automations)
    
    @pytest.mark.asyncio
    async def test_create_without_id(self, file_manager):
        """Test creating automation without ID (generates one)."""
        automation = Automation(
            alias="No ID Automation",
            trigger=[{"platform": "state"}],
            action=[{"service": "test"}],
        )
        
        result_id = await file_manager.create(automation)
        
        # Should generate a file-friendly ID
        assert result_id is not None
        assert "no_id_automation" in result_id.lower()
        assert len(result_id) > 10  # Has timestamp
    
    @pytest.mark.asyncio
    async def test_create_with_ui_id_rejected(self, file_manager):
        """Test creating automation with UI-style ID is rejected."""
        automation = Automation(
            id="1234567890abcdef1234567890abcdef",
            alias="UI Style ID",
            trigger=[],
            action=[],
        )
        
        with pytest.raises(ValidationError, match="should not use UI-style IDs"):
            await file_manager.create(automation)
    
    @pytest.mark.asyncio
    async def test_create_duplicate_id(self, file_manager):
        """Test creating automation with duplicate ID."""
        automation = Automation(
            id="existing_automation",
            alias="Duplicate",
            trigger=[],
            action=[],
        )
        
        with pytest.raises(ValidationError, match="already exists"):
            await file_manager.create(automation)
    
    @pytest.mark.asyncio
    async def test_update(self, file_manager):
        """Test updating existing automation."""
        automation = Automation(
            id="existing_automation",
            alias="Updated Existing Automation",
            trigger=[{"platform": "mqtt", "topic": "test/topic"}],
            action=[{"service": "script.test"}],
        )
        
        await file_manager.update(automation)
        
        # Verify update
        automations = await file_manager.load_all()
        updated = next(a for a in automations if a.id == "existing_automation")
        assert updated.alias == "Updated Existing Automation"
        assert updated.trigger[0]["platform"] == "mqtt"
    
    @pytest.mark.asyncio
    async def test_update_without_id(self, file_manager):
        """Test updating automation without ID."""
        automation = Automation(
            alias="No ID",
            trigger=[],
            action=[],
        )
        
        with pytest.raises(ValidationError, match="ID is required"):
            await file_manager.update(automation)
    
    @pytest.mark.asyncio
    async def test_update_not_found(self, file_manager):
        """Test updating non-existent automation."""
        automation = Automation(
            id="nonexistent",
            alias="Not Found",
            trigger=[],
            action=[],
        )
        
        with pytest.raises(NotFoundError):
            await file_manager.update(automation)
    
    @pytest.mark.asyncio
    async def test_delete(self, file_manager):
        """Test deleting automation."""
        await file_manager.delete("existing_automation")
        
        # Verify deletion
        automations = await file_manager.load_all()
        assert len(automations) == 1
        assert not any(a.id == "existing_automation" for a in automations)
    
    @pytest.mark.asyncio
    async def test_delete_not_found(self, file_manager):
        """Test deleting non-existent automation."""
        with pytest.raises(NotFoundError):
            await file_manager.delete("nonexistent")
    
    @pytest.mark.asyncio
    async def test_get_by_id(self, file_manager):
        """Test getting automation by ID."""
        automation = await file_manager.get_by_id("existing_automation")
        
        assert automation is not None
        assert automation.id == "existing_automation"
        assert automation.alias == "Existing Automation"
    
    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, file_manager):
        """Test getting non-existent automation."""
        automation = await file_manager.get_by_id("nonexistent")
        assert automation is None
    
    @pytest.mark.asyncio
    async def test_exists(self, file_manager):
        """Test checking if automation exists."""
        assert await file_manager.exists("existing_automation") is True
        assert await file_manager.exists("nonexistent") is False
    
    @pytest.mark.asyncio
    async def test_backup_creation(self, file_manager, temp_automations_file):
        """Test backup file creation."""
        # Make a change
        await file_manager.save_all([])
        
        # Check backup was created
        backups = list(temp_automations_file.parent.glob(f"{temp_automations_file.stem}.*.backup"))
        assert len(backups) == 1
    
    @pytest.mark.asyncio
    async def test_backup_cleanup(self, file_manager, temp_automations_file):
        """Test old backup cleanup."""
        # Create multiple backups by making changes
        for i in range(8):
            await file_manager.save_all([
                Automation(
                    id=f"test_{i}",
                    alias=f"Test {i}",
                    trigger=[],
                    action=[],
                )
            ])
            # Small delay to ensure different timestamps
            await asyncio.sleep(0.01)
        
        # Should keep only last 5 backups
        backups = list(temp_automations_file.parent.glob(f"{temp_automations_file.stem}.*.backup"))
        assert len(backups) <= 5
    
    @pytest.mark.asyncio
    async def test_generate_file_id(self, file_manager):
        """Test file ID generation."""
        # Test various alias formats
        test_cases = [
            ("My Automation", "my_automation_"),
            ("Turn-on-lights", "turn_on_lights_"),
            ("Temperature > 25", "temperature_25_"),
            ("  Spaces  Around  ", "spaces_around_"),
            ("CamelCaseTest", "camelcasetest_"),
        ]
        
        for alias, expected_prefix in test_cases:
            generated_id = file_manager._generate_file_id(alias)
            assert generated_id.startswith(expected_prefix)
            assert len(generated_id) > len(expected_prefix) + 10  # Has timestamp
    
    @pytest.mark.asyncio
    async def test_format_preservation(self, file_manager):
        """Test that YAML formatting is preserved."""
        # Create automation with various formats
        automation = Automation(
            id="format_test",
            alias="Format Test",
            trigger=[
                {
                    "platform": "state",
                    "entity_id": ["sensor.one", "sensor.two"],
                    "to": "on",
                }
            ],
            condition=[
                {
                    "condition": "numeric_state",
                    "entity_id": "sensor.temperature",
                    "above": 20,
                    "below": 30,
                }
            ],
            action=[
                {
                    "service": "notify.notify",
                    "data": {
                        "message": "Temperature is {{ states('sensor.temperature') }}",
                        "title": "Temperature Alert",
                    }
                }
            ],
            variables={
                "temp_threshold": 25,
                "alert_enabled": True,
            },
        )
        
        await file_manager.save_all([automation])
        
        # Load and verify structure is maintained
        loaded = await file_manager.load_all()
        assert len(loaded) == 1
        assert loaded[0].trigger[0]["entity_id"] == ["sensor.one", "sensor.two"]
        assert loaded[0].variables["temp_threshold"] == 25
        assert loaded[0].variables["alert_enabled"] is True


# Add missing import
import asyncio