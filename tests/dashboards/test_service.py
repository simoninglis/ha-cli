"""Tests for dashboard service."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import ruamel.yaml

from ha_cli.common.exceptions import NotFoundError, ValidationError
from ha_cli.domains.dashboards.models import DashboardConfig, DashboardInfo
from ha_cli.domains.dashboards.service import DashboardService


@pytest.fixture
def mock_client():
    """Create mock HAClient."""
    client = AsyncMock()
    return client


@pytest.fixture
def dashboard_service(mock_client):
    """Create DashboardService instance."""
    return DashboardService(mock_client)


@pytest.fixture
def sample_dashboard_list():
    """Sample dashboard list response."""
    return [
        {
            "id": "mobile",
            "url_path": "mobile",
            "title": "Mobile Dashboard",
            "icon": "mdi:cellphone",
            "require_admin": False,
            "show_in_sidebar": True,
            "mode": "storage",
        },
        {
            "id": "tablet",
            "url_path": "tablet",
            "title": "Tablet Dashboard",
            "icon": "mdi:tablet",
            "require_admin": False,
            "show_in_sidebar": True,
            "mode": "yaml",
        },
    ]


@pytest.fixture
def sample_dashboard_config():
    """Sample dashboard configuration."""
    return {
        "title": "Test Dashboard",
        "version": 1,
        "views": [
            {
                "title": "Home",
                "path": "home",
                "cards": [
                    {
                        "type": "entities",
                        "title": "Lights",
                        "entities": ["light.living_room", "light.bedroom"],
                    },
                    {
                        "type": "button",
                        "entity": "switch.fan",
                        "tap_action": {
                            "action": "toggle"
                        }
                    }
                ]
            },
            {
                "title": "Climate",
                "path": "climate",
                "cards": [
                    {
                        "type": "thermostat",
                        "entity": "climate.living_room",
                    }
                ]
            }
        ]
    }


class TestDashboardService:
    """Test DashboardService class."""
    
    @pytest.mark.asyncio
    async def test_list_dashboards_default(self, dashboard_service, mock_client, sample_dashboard_list):
        """Test listing dashboards with default included."""
        mock_client.list_dashboards.return_value = sample_dashboard_list
        
        dashboards = await dashboard_service.list_dashboards()
        
        assert len(dashboards) == 3  # default + 2 from API
        
        # Check default dashboard
        assert dashboards[0].id == "default"
        assert dashboards[0].url_path == ""
        assert dashboards[0].title == "Default"
        assert dashboards[0].mode == "storage"
        
        # Check other dashboards
        assert dashboards[1].id == "mobile"
        assert dashboards[1].url_path == "mobile"
        assert dashboards[2].id == "tablet"
        assert dashboards[2].mode == "yaml"
    
    @pytest.mark.asyncio
    async def test_list_dashboards_no_default(self, dashboard_service, mock_client, sample_dashboard_list):
        """Test listing dashboards without default."""
        mock_client.list_dashboards.return_value = sample_dashboard_list
        
        dashboards = await dashboard_service.list_dashboards(include_default=False)
        
        assert len(dashboards) == 2
        assert all(d.id != "default" for d in dashboards)
    
    @pytest.mark.asyncio
    async def test_get_dashboard(self, dashboard_service, mock_client, sample_dashboard_config):
        """Test getting dashboard configuration."""
        mock_client.get_dashboard_config.return_value = sample_dashboard_config
        
        config = await dashboard_service.get_dashboard("mobile")
        
        mock_client.get_dashboard_config.assert_called_once_with("mobile")
        assert isinstance(config, DashboardConfig)
        assert config.title == "Test Dashboard"
        assert len(config.views) == 2
        assert config.views[0].title == "Home"
    
    @pytest.mark.asyncio
    async def test_get_dashboard_default(self, dashboard_service, mock_client, sample_dashboard_config):
        """Test getting default dashboard."""
        mock_client.get_dashboard_config.return_value = sample_dashboard_config
        
        config = await dashboard_service.get_dashboard(None)
        
        mock_client.get_dashboard_config.assert_called_once_with(None)
        assert isinstance(config, DashboardConfig)
    
    @pytest.mark.asyncio
    async def test_save_dashboard(self, dashboard_service, mock_client):
        """Test saving dashboard configuration."""
        config = DashboardConfig(
            title="New Dashboard",
            views=[]
        )
        
        await dashboard_service.save_dashboard(config, "test")
        
        mock_client.save_dashboard_config.assert_called_once()
        args = mock_client.save_dashboard_config.call_args
        assert args[0][0]["title"] == "New Dashboard"
        assert args[0][1] == "test"
    
    @pytest.mark.asyncio
    async def test_create_dashboard(self, dashboard_service, mock_client):
        """Test creating new dashboard."""
        await dashboard_service.create_dashboard(
            dashboard_id="new-dash",
            url_path="new",
            title="New Dashboard",
            icon="mdi:new-box",
            show_in_sidebar=True,
            require_admin=False,
        )
        
        mock_client.create_dashboard.assert_called_once_with(
            dashboard_id="new-dash",
            url_path="new",
            title="New Dashboard",
            icon="mdi:new-box",
            show_in_sidebar=True,
            require_admin=False,
        )
    
    @pytest.mark.asyncio
    async def test_update_dashboard(self, dashboard_service, mock_client):
        """Test updating dashboard settings."""
        await dashboard_service.update_dashboard(
            dashboard_id="mobile",
            title="Updated Mobile",
            icon="mdi:phone",
        )
        
        mock_client.update_dashboard.assert_called_once_with(
            dashboard_id="mobile",
            url_path=None,
            title="Updated Mobile",
            icon="mdi:phone",
            show_in_sidebar=None,
            require_admin=None,
        )
    
    @pytest.mark.asyncio
    async def test_delete_dashboard(self, dashboard_service, mock_client):
        """Test deleting dashboard."""
        await dashboard_service.delete_dashboard("mobile")
        
        mock_client.delete_dashboard.assert_called_once_with("mobile")
    
    @pytest.mark.asyncio
    async def test_backup_dashboard_yaml(self, dashboard_service, mock_client, sample_dashboard_config, tmp_path):
        """Test backing up dashboard to YAML file."""
        mock_client.get_dashboard_config.return_value = sample_dashboard_config
        
        # Use tmp_path for output
        output_file = str(tmp_path / "backup.yaml")
        
        result = await dashboard_service.backup_dashboard(
            url_path="mobile",
            output_file=output_file,
            format="yaml"
        )
        
        assert result == output_file
        assert Path(output_file).exists()
        
        # Verify content
        yaml = ruamel.yaml.YAML(typ='safe')
        with open(output_file) as f:
            data = yaml.load(f)
        
        assert data["title"] == "Test Dashboard"
        assert len(data["views"]) == 2
    
    @pytest.mark.asyncio
    async def test_backup_dashboard_json(self, dashboard_service, mock_client, sample_dashboard_config, tmp_path):
        """Test backing up dashboard to JSON file."""
        mock_client.get_dashboard_config.return_value = sample_dashboard_config
        
        output_file = str(tmp_path / "backup.json")
        
        result = await dashboard_service.backup_dashboard(
            url_path="mobile",
            output_file=output_file,
            format="json"
        )
        
        assert result == output_file
        assert Path(output_file).exists()
        
        # Verify content
        with open(output_file) as f:
            data = json.load(f)
        
        assert data["title"] == "Test Dashboard"
        assert len(data["views"]) == 2
    
    @pytest.mark.asyncio
    async def test_backup_dashboard_auto_filename(self, dashboard_service, mock_client, sample_dashboard_config):
        """Test backup with auto-generated filename."""
        mock_client.get_dashboard_config.return_value = sample_dashboard_config
        
        with patch("ha_cli.domains.dashboards.service.Path.open", MagicMock()):
            with patch("ha_cli.domains.dashboards.service.ruamel.yaml.YAML.dump"):
                result = await dashboard_service.backup_dashboard(url_path="mobile")
        
        # Should generate filename with timestamp
        assert "dashboard_mobile_" in result
        assert ".yaml" in result
    
    @pytest.mark.asyncio
    async def test_restore_dashboard_yaml(self, dashboard_service, mock_client, sample_dashboard_config, tmp_path):
        """Test restoring dashboard from YAML file."""
        # Create backup file
        yaml = ruamel.yaml.YAML()
        backup_file = tmp_path / "backup.yaml"
        with open(backup_file, "w") as f:
            yaml.dump(sample_dashboard_config, f)
        
        await dashboard_service.restore_dashboard(str(backup_file), "mobile")
        
        mock_client.save_dashboard_config.assert_called_once()
        args = mock_client.save_dashboard_config.call_args
        assert args[0][0]["title"] == "Test Dashboard"
        assert args[0][1] == "mobile"
    
    @pytest.mark.asyncio
    async def test_restore_dashboard_json(self, dashboard_service, mock_client, sample_dashboard_config, tmp_path):
        """Test restoring dashboard from JSON file."""
        # Create backup file
        backup_file = tmp_path / "backup.json"
        with open(backup_file, "w") as f:
            json.dump(sample_dashboard_config, f)
        
        await dashboard_service.restore_dashboard(str(backup_file), "mobile")
        
        mock_client.save_dashboard_config.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_restore_dashboard_validate_only(self, dashboard_service, mock_client, sample_dashboard_config, tmp_path):
        """Test validating dashboard without restoring."""
        # Create backup file
        backup_file = tmp_path / "backup.yaml"
        yaml = ruamel.yaml.YAML()
        with open(backup_file, "w") as f:
            yaml.dump(sample_dashboard_config, f)
        
        await dashboard_service.restore_dashboard(
            str(backup_file),
            "mobile",
            validate_only=True
        )
        
        # Should not call save
        mock_client.save_dashboard_config.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_restore_dashboard_file_not_found(self, dashboard_service):
        """Test restore with non-existent file."""
        with pytest.raises(ValidationError) as exc_info:
            await dashboard_service.restore_dashboard("nonexistent.yaml")
        
        assert "File not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_entity_references(self, dashboard_service, mock_client, sample_dashboard_config):
        """Test extracting entity references."""
        mock_client.get_dashboard_config.return_value = sample_dashboard_config
        
        entities = await dashboard_service.get_entity_references("mobile")
        
        assert len(entities) == 4
        assert "light.living_room" in entities
        assert "light.bedroom" in entities
        assert "switch.fan" in entities
        assert "climate.living_room" in entities
    
    @pytest.mark.asyncio
    async def test_update_entity_references(self, dashboard_service, mock_client, sample_dashboard_config):
        """Test updating entity references."""
        mock_client.get_dashboard_config.return_value = sample_dashboard_config
        
        entity_map = {
            "light.living_room": "light.living_room_main",
            "switch.fan": "fan.living_room",
            "sensor.missing": "sensor.new",  # Not in dashboard
        }
        
        result = await dashboard_service.update_entity_references(
            url_path="mobile",
            entity_map=entity_map,
            dry_run=False
        )
        
        assert len(result["updated"]) == 2
        assert "light.living_room" in result["updated"]
        assert "switch.fan" in result["updated"]
        
        assert len(result["not_found"]) == 1
        assert "sensor.missing" in result["not_found"]
        
        # Verify save was called
        mock_client.save_dashboard_config.assert_called_once()
        
        # Check the updated config
        args = mock_client.save_dashboard_config.call_args
        config_dict = args[0][0]
        
        # Verify entities were updated
        card_entities = config_dict["views"][0]["cards"][0]["entities"]
        assert "light.living_room_main" in card_entities
        assert "light.living_room" not in card_entities
        
        button_entity = config_dict["views"][0]["cards"][1]["entity"]
        assert button_entity == "fan.living_room"
    
    @pytest.mark.asyncio
    async def test_update_entity_references_dry_run(self, dashboard_service, mock_client, sample_dashboard_config):
        """Test updating entity references in dry run mode."""
        mock_client.get_dashboard_config.return_value = sample_dashboard_config
        
        entity_map = {
            "light.living_room": "light.living_room_main",
        }
        
        result = await dashboard_service.update_entity_references(
            url_path="mobile",
            entity_map=entity_map,
            dry_run=True
        )
        
        assert len(result["updated"]) == 1
        
        # Should not save in dry run
        mock_client.save_dashboard_config.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_update_entity_references_no_map(self, dashboard_service):
        """Test update entity references without map."""
        with pytest.raises(ValidationError) as exc_info:
            await dashboard_service.update_entity_references()
        
        assert "Entity map is required" in str(exc_info.value)