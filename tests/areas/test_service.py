"""Tests for areas domain service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_cli.common.exceptions import NotFoundError, ValidationError
from ha_cli.domains.areas.service import AreaService


@pytest.fixture()
def mock_client() -> MagicMock:
    """Create mock HA client."""
    client = MagicMock()
    client._ws_call = AsyncMock()
    return client


@pytest.fixture()
def service(mock_client: MagicMock) -> AreaService:
    """Create area service with mock client."""
    return AreaService(mock_client)


class TestAreaService:
    """Test AreaService."""

    @pytest.mark.asyncio()
    async def test_list_areas(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test listing areas."""
        mock_client._ws_call.return_value = [
            {"area_id": "kitchen", "name": "Kitchen"},
            {"area_id": "bedroom", "name": "Bedroom"},
        ]
        areas = await service.list_areas()
        assert len(areas) == 2
        # Should be sorted by name
        assert areas[0].name == "Bedroom"
        assert areas[1].name == "Kitchen"

    @pytest.mark.asyncio()
    async def test_list_devices(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test listing devices."""
        mock_client._ws_call.return_value = [
            {"id": "dev1", "name": "Device 1", "area_id": "kitchen"},
            {"id": "dev2", "name": "Device 2"},
        ]
        devices = await service.list_devices()
        assert len(devices) == 2
        assert devices[0].id == "dev1"
        assert devices[0].area_id == "kitchen"

    @pytest.mark.asyncio()
    async def test_list_floors(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test listing floors."""
        mock_client._ws_call.return_value = [
            {"floor_id": "second", "name": "Second Floor", "level": 2},
            {"floor_id": "ground", "name": "Ground Floor", "level": 0},
            {"floor_id": "first", "name": "First Floor", "level": 1},
        ]
        floors = await service.list_floors()
        assert len(floors) == 3
        # Should be sorted by level
        assert floors[0].name == "Ground Floor"
        assert floors[1].name == "First Floor"
        assert floors[2].name == "Second Floor"

    @pytest.mark.asyncio()
    async def test_list_labels(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test listing labels."""
        mock_client._ws_call.return_value = [
            {"label_id": "important", "name": "Important"},
            {"label_id": "alpha", "name": "Alpha"},
        ]
        labels = await service.list_labels()
        assert len(labels) == 2
        # Should be sorted by name
        assert labels[0].name == "Alpha"
        assert labels[1].name == "Important"

    @pytest.mark.asyncio()
    async def test_list_areas_with_counts(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test listing areas with device and entity counts."""
        # Mock responses for areas, devices, and entities
        mock_client._ws_call.side_effect = [
            # Areas
            [{"area_id": "kitchen", "name": "Kitchen"}],
            # Devices
            [
                {"id": "dev1", "name": "Device 1", "area_id": "kitchen"},
                {"id": "dev2", "name": "Device 2", "area_id": "kitchen"},
            ],
            # Entities
            [
                {"entity_id": "light.kitchen", "area_id": "kitchen", "platform": "hue"},
                {"entity_id": "sensor.temp", "area_id": None, "platform": "temp"},
            ],
        ]
        areas = await service.list_areas_with_counts()
        assert len(areas) == 1
        assert areas[0].device_count == 2
        assert areas[0].entity_count == 1

    @pytest.mark.asyncio()
    async def test_get_area_by_id(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test getting area by ID."""
        mock_client._ws_call.side_effect = [
            [{"area_id": "kitchen", "name": "Kitchen"}],
            [],  # devices
            [],  # entities
        ]
        area = await service.get_area("kitchen")
        assert area is not None
        assert area.name == "Kitchen"

    @pytest.mark.asyncio()
    async def test_get_area_by_name(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test getting area by name (case-insensitive)."""
        mock_client._ws_call.side_effect = [
            [{"area_id": "kitchen", "name": "Kitchen"}],
            [],
            [],
        ]
        area = await service.get_area("KITCHEN")
        assert area is not None
        assert area.area_id == "kitchen"

    @pytest.mark.asyncio()
    async def test_get_area_not_found(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test getting non-existent area."""
        mock_client._ws_call.side_effect = [
            [{"area_id": "kitchen", "name": "Kitchen"}],
            [],
            [],
        ]
        area = await service.get_area("nonexistent")
        assert area is None

    @pytest.mark.asyncio()
    async def test_get_area_summary(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test getting area summary statistics."""
        mock_client._ws_call.side_effect = [
            # areas (for list_areas_with_counts)
            [{"area_id": "kitchen", "name": "Kitchen"}],
            # devices (for list_areas_with_counts)
            [{"id": "dev1", "area_id": "kitchen"}],
            # entities (for list_areas_with_counts)
            [{"entity_id": "light.kitchen", "area_id": "kitchen", "platform": "hue"}],
            # devices (for get_area_summary)
            [{"id": "dev1", "area_id": "kitchen"}, {"id": "dev2", "area_id": None}],
            # entities (for get_area_summary)
            [
                {"entity_id": "light.kitchen", "area_id": "kitchen", "platform": "hue"},
                {"entity_id": "sensor.temp", "area_id": None, "platform": "temp"},
            ],
        ]
        summary = await service.get_area_summary()
        assert summary["total_areas"] == 1
        assert summary["total_devices"] == 2
        assert summary["devices_with_area"] == 1
        assert summary["devices_without_area"] == 1

    @pytest.mark.asyncio()
    async def test_check_naming_issues_typo(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test detecting typos in area names."""
        mock_client._ws_call.return_value = [
            {"area_id": "garrage", "name": "Garrage"},  # Typo!
        ]
        issues = await service.check_naming_issues()
        assert len(issues) > 0
        typo_issues = [i for i in issues if i["issue_type"] == "possible_typo"]
        assert len(typo_issues) == 1
        assert "garrage" in typo_issues[0]["message"].lower()

    @pytest.mark.asyncio()
    async def test_check_naming_issues_device_name(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test detecting device-like area names."""
        mock_client._ws_call.return_value = [
            {"area_id": "sonos_roam", "name": "Sonos Roam"},
        ]
        issues = await service.check_naming_issues()
        device_issues = [i for i in issues if i["issue_type"] == "device_name"]
        assert len(device_issues) == 1

    @pytest.mark.asyncio()
    async def test_find_empty_areas(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test finding empty areas."""
        mock_client._ws_call.side_effect = [
            [
                {"area_id": "kitchen", "name": "Kitchen"},
                {"area_id": "empty_room", "name": "Empty Room"},
            ],
            [{"id": "dev1", "area_id": "kitchen"}],  # Kitchen has device
            [{"entity_id": "light.kitchen", "area_id": "kitchen", "platform": "hue"}],
        ]
        empty = await service.find_empty_areas()
        assert len(empty) == 1
        assert empty[0].name == "Empty Room"

    @pytest.mark.asyncio()
    async def test_get_unassigned_devices(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test getting devices without area assignment."""
        mock_client._ws_call.return_value = [
            {"id": "dev1", "area_id": "kitchen"},
            {"id": "dev2", "area_id": None},
            {"id": "dev3", "area_id": None, "disabled_by": "user"},  # Should exclude
        ]
        unassigned = await service.get_unassigned_devices()
        assert len(unassigned) == 1
        assert unassigned[0].id == "dev2"

    @pytest.mark.asyncio()
    async def test_get_unassigned_entities(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test getting entities without area assignment."""
        mock_client._ws_call.side_effect = [
            # Entities
            [
                {
                    "entity_id": "light.kitchen",
                    "area_id": "kitchen",
                    "platform": "hue",
                },
                {
                    "entity_id": "sensor.temp",
                    "area_id": None,
                    "device_id": "dev1",
                    "platform": "temp",
                },
                {
                    "entity_id": "sensor.orphan",
                    "area_id": None,
                    "device_id": None,
                    "platform": "temp",
                },
            ],
            # Devices
            [{"id": "dev1", "area_id": "kitchen"}],  # dev1 has area
        ]
        unassigned = await service.get_unassigned_entities()
        assert len(unassigned) == 1
        assert unassigned[0].entity_id == "sensor.orphan"


class TestAreaServiceCRUD:
    """Test AreaService CRUD operations."""

    @pytest.mark.asyncio()
    async def test_create_area_success(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test creating an area successfully."""
        mock_client._ws_call.return_value = {
            "area_id": "new_area",
            "name": "New Area",
            "icon": "mdi:home",
        }
        area = await service.create_area(name="New Area", icon="mdi:home")
        assert area.area_id == "new_area"
        assert area.name == "New Area"
        assert area.icon == "mdi:home"
        mock_client._ws_call.assert_called_once_with(
            "config/area_registry/create",
            name="New Area",
            icon="mdi:home",
        )

    @pytest.mark.asyncio()
    async def test_create_area_with_all_options(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test creating an area with all optional parameters."""
        mock_client._ws_call.return_value = {
            "area_id": "new_area",
            "name": "New Area",
            "floor_id": "ground",
            "icon": "mdi:home",
            "aliases": ["alias1", "alias2"],
            "labels": ["label1"],
        }
        area = await service.create_area(
            name="New Area",
            floor_id="ground",
            icon="mdi:home",
            aliases=["alias1", "alias2"],
            labels=["label1"],
        )
        assert area.name == "New Area"
        assert area.floor_id == "ground"
        mock_client._ws_call.assert_called_once()

    @pytest.mark.asyncio()
    async def test_create_area_duplicate(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test creating an area with a name that already exists."""
        mock_client._ws_call.side_effect = Exception(
            "name is already in use"
        )
        with pytest.raises(ValidationError, match="already exists"):
            await service.create_area(name="Existing Area")

    @pytest.mark.asyncio()
    async def test_update_area_success(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test updating an area successfully."""
        mock_client._ws_call.return_value = {
            "area_id": "kitchen",
            "name": "Updated Kitchen",
            "icon": "mdi:silverware-fork-knife",
        }
        area = await service.update_area(
            area_id="kitchen",
            name="Updated Kitchen",
            icon="mdi:silverware-fork-knife",
        )
        assert area.name == "Updated Kitchen"
        assert area.icon == "mdi:silverware-fork-knife"

    @pytest.mark.asyncio()
    async def test_update_area_not_found(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test updating a non-existent area."""
        mock_client._ws_call.side_effect = Exception("unknown area")
        with pytest.raises(NotFoundError, match="not found"):
            await service.update_area(area_id="nonexistent", name="New Name")

    @pytest.mark.asyncio()
    async def test_update_area_name_conflict(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test updating area to a name that already exists."""
        mock_client._ws_call.side_effect = Exception(
            "name is already in use"
        )
        with pytest.raises(ValidationError, match="already in use"):
            await service.update_area(area_id="kitchen", name="Living Room")

    @pytest.mark.asyncio()
    async def test_rename_area_success(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test renaming an area (convenience method)."""
        mock_client._ws_call.return_value = {
            "area_id": "kitchen",
            "name": "New Kitchen Name",
        }
        area = await service.rename_area("kitchen", "New Kitchen Name")
        assert area.name == "New Kitchen Name"
        mock_client._ws_call.assert_called_once_with(
            "config/area_registry/update",
            area_id="kitchen",
            name="New Kitchen Name",
        )

    @pytest.mark.asyncio()
    async def test_delete_area_success(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test deleting an empty area."""
        # Mock for get_area check (empty area)
        mock_client._ws_call.side_effect = [
            # list_areas
            [{"area_id": "empty_room", "name": "Empty Room"}],
            # list_devices
            [],
            # list_entities
            [],
            # delete
            None,
        ]
        await service.delete_area("empty_room")
        # Verify delete was called
        assert mock_client._ws_call.call_count == 4

    @pytest.mark.asyncio()
    async def test_delete_area_with_contents_no_force(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test deleting area with devices/entities without force flag."""
        mock_client._ws_call.side_effect = [
            # list_areas
            [{"area_id": "kitchen", "name": "Kitchen"}],
            # list_devices
            [{"id": "dev1", "name": "Device 1", "area_id": "kitchen"}],
            # list_entities
            [{"entity_id": "light.kitchen", "area_id": "kitchen", "platform": "hue"}],
        ]
        with pytest.raises(ValidationError, match="has 1 devices"):
            await service.delete_area("kitchen")

    @pytest.mark.asyncio()
    async def test_delete_area_with_force(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test deleting area with force flag skips safety check."""
        mock_client._ws_call.return_value = None
        await service.delete_area("kitchen", force=True)
        mock_client._ws_call.assert_called_once_with(
            "config/area_registry/delete",
            area_id="kitchen",
        )

    @pytest.mark.asyncio()
    async def test_delete_area_not_found(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test deleting a non-existent area."""
        mock_client._ws_call.side_effect = [
            # list_areas (for get_area check)
            [],
            # list_devices
            [],
            # list_entities
            [],
        ]
        with pytest.raises(NotFoundError, match="not found"):
            await service.delete_area("nonexistent")

    @pytest.mark.asyncio()
    async def test_delete_area_force_not_found(
        self, service: AreaService, mock_client: MagicMock
    ) -> None:
        """Test deleting non-existent area with force flag."""
        mock_client._ws_call.side_effect = Exception("unknown area")
        with pytest.raises(NotFoundError, match="not found"):
            await service.delete_area("nonexistent", force=True)
