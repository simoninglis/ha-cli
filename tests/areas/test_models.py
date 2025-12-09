"""Tests for areas domain models."""

from ha_cli.domains.areas.models import (
    Area,
    AreaWithCounts,
    Device,
    EntityRegistryEntry,
    Floor,
    Label,
)


class TestArea:
    """Test Area model."""

    def test_from_dict_minimal(self) -> None:
        """Test creating area from minimal dict."""
        data = {"area_id": "living_room", "name": "Living Room"}
        area = Area.from_dict(data)
        assert area.area_id == "living_room"
        assert area.name == "Living Room"
        assert area.aliases == []
        assert area.floor_id is None

    def test_from_dict_full(self) -> None:
        """Test creating area from full dict."""
        data = {
            "area_id": "living_room",
            "name": "Living Room",
            "aliases": ["lounge", "front room"],
            "floor_id": "ground_floor",
            "icon": "mdi:sofa",
            "labels": ["main_floor"],
            "picture": "/local/living.jpg",
        }
        area = Area.from_dict(data)
        assert area.area_id == "living_room"
        assert area.name == "Living Room"
        assert area.aliases == ["lounge", "front room"]
        assert area.floor_id == "ground_floor"
        assert area.icon == "mdi:sofa"
        assert area.labels == ["main_floor"]
        assert area.picture == "/local/living.jpg"

    def test_to_dict(self) -> None:
        """Test converting area to dict."""
        area = Area(
            area_id="kitchen",
            name="Kitchen",
            floor_id="ground_floor",
        )
        result = area.to_dict()
        assert result["area_id"] == "kitchen"
        assert result["name"] == "Kitchen"
        assert result["floor_id"] == "ground_floor"
        assert "aliases" not in result  # Empty list not included


class TestAreaWithCounts:
    """Test AreaWithCounts model."""

    def test_from_area(self) -> None:
        """Test creating AreaWithCounts from Area."""
        area = Area(area_id="bedroom", name="Bedroom")
        area_with_counts = AreaWithCounts.from_area(
            area,
            device_count=5,
            entity_count=20,
            devices=["lamp", "sensor"],
            entities=["light.bedroom", "sensor.temp"],
        )
        assert area_with_counts.area_id == "bedroom"
        assert area_with_counts.name == "Bedroom"
        assert area_with_counts.device_count == 5
        assert area_with_counts.entity_count == 20
        assert len(area_with_counts.devices) == 2

    def test_to_dict_includes_counts(self) -> None:
        """Test that to_dict includes counts."""
        area = Area(area_id="garage", name="Garage")
        area_with_counts = AreaWithCounts.from_area(area, device_count=3)
        result = area_with_counts.to_dict()
        assert result["device_count"] == 3
        assert result["entity_count"] == 0


class TestDevice:
    """Test Device model."""

    def test_from_dict(self) -> None:
        """Test creating device from dict."""
        data = {
            "id": "abc123",
            "name": "Hue Bridge",
            "name_by_user": "My Hue",
            "area_id": "living_room",
            "manufacturer": "Philips",
            "model": "BSB002",
        }
        device = Device.from_dict(data)
        assert device.id == "abc123"
        assert device.name == "Hue Bridge"
        assert device.name_by_user == "My Hue"
        assert device.display_name == "My Hue"

    def test_display_name_fallback(self) -> None:
        """Test display name fallback to device name."""
        device = Device(id="xyz", name="Device Name")
        assert device.display_name == "Device Name"

    def test_display_name_fallback_to_id(self) -> None:
        """Test display name fallback to ID."""
        device = Device(id="xyz")
        assert device.display_name == "xyz"


class TestFloor:
    """Test Floor model."""

    def test_from_dict(self) -> None:
        """Test creating floor from dict."""
        data = {
            "floor_id": "ground",
            "name": "Ground Floor",
            "level": 0,
            "icon": "mdi:home-floor-0",
        }
        floor = Floor.from_dict(data)
        assert floor.floor_id == "ground"
        assert floor.name == "Ground Floor"
        assert floor.level == 0
        assert floor.icon == "mdi:home-floor-0"

    def test_to_dict(self) -> None:
        """Test converting floor to dict."""
        floor = Floor(floor_id="first", name="First Floor", level=1)
        result = floor.to_dict()
        assert result["floor_id"] == "first"
        assert result["level"] == 1


class TestLabel:
    """Test Label model."""

    def test_from_dict(self) -> None:
        """Test creating label from dict."""
        data = {
            "label_id": "important",
            "name": "Important",
            "color": "red",
            "description": "Important items",
        }
        label = Label.from_dict(data)
        assert label.label_id == "important"
        assert label.name == "Important"
        assert label.color == "red"

    def test_to_dict(self) -> None:
        """Test converting label to dict."""
        label = Label(label_id="test", name="Test", color="blue")
        result = label.to_dict()
        assert result["label_id"] == "test"
        assert result["name"] == "Test"
        assert result["color"] == "blue"


class TestEntityRegistryEntry:
    """Test EntityRegistryEntry model."""

    def test_from_dict(self) -> None:
        """Test creating entity from dict."""
        data = {
            "entity_id": "light.kitchen",
            "unique_id": "abc123",
            "platform": "hue",
            "area_id": "kitchen",
            "device_id": "dev123",
        }
        entity = EntityRegistryEntry.from_dict(data)
        assert entity.entity_id == "light.kitchen"
        assert entity.platform == "hue"
        assert entity.area_id == "kitchen"
