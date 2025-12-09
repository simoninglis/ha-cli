"""Tests for areas domain service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

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
