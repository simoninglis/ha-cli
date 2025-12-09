"""Service layer for areas domain."""

import logging
import re
from typing import Any, cast

from ...common.client import HAClient
from .models import Area, AreaWithCounts, Device, EntityRegistryEntry, Floor, Label

logger = logging.getLogger(__name__)


class AreaService:
    """Service for managing Home Assistant areas and registry metadata."""

    def __init__(self, client: HAClient) -> None:
        """Initialize area service.

        Args:
            client: Home Assistant client
        """
        self.client = client

    async def list_areas(self) -> list[Area]:
        """Get all areas from the area registry.

        Returns:
            List of areas
        """
        result = await self.client._ws_call("config/area_registry/list")
        result_list = cast(list[dict[str, Any]], result)
        areas = []
        for item in result_list:
            areas.append(Area.from_dict(item))
        return sorted(areas, key=lambda a: a.name.lower())

    async def list_devices(self) -> list[Device]:
        """Get all devices from the device registry.

        Returns:
            List of devices
        """
        result = await self.client._ws_call("config/device_registry/list")
        result_list = cast(list[dict[str, Any]], result)
        devices = []
        for item in result_list:
            devices.append(Device.from_dict(item))
        return devices

    async def list_entity_registry(self) -> list[EntityRegistryEntry]:
        """Get all entities from the entity registry.

        Returns:
            List of entity registry entries
        """
        result = await self.client._ws_call("config/entity_registry/list")
        result_list = cast(list[dict[str, Any]], result)
        entities = []
        for item in result_list:
            entities.append(EntityRegistryEntry.from_dict(item))
        return entities

    async def list_floors(self) -> list[Floor]:
        """Get all floors from the floor registry.

        Returns:
            List of floors
        """
        result = await self.client._ws_call("config/floor_registry/list")
        result_list = cast(list[dict[str, Any]], result)
        floors = []
        for item in result_list:
            floors.append(Floor.from_dict(item))
        return sorted(floors, key=lambda f: f.level)

    async def list_labels(self) -> list[Label]:
        """Get all labels from the label registry.

        Returns:
            List of labels
        """
        result = await self.client._ws_call("config/label_registry/list")
        result_list = cast(list[dict[str, Any]], result)
        labels = []
        for item in result_list:
            labels.append(Label.from_dict(item))
        return sorted(labels, key=lambda lbl: lbl.name.lower())

    async def list_areas_with_counts(self) -> list[AreaWithCounts]:
        """Get all areas with device and entity counts.

        Returns:
            List of areas with counts
        """
        # Fetch all data in parallel would be ideal, but we need to do it sequentially
        areas = await self.list_areas()
        devices = await self.list_devices()
        entities = await self.list_entity_registry()

        # Build lookup maps
        devices_by_area: dict[str, list[str]] = {}
        entities_by_area: dict[str, list[str]] = {}

        for device in devices:
            if device.area_id:
                if device.area_id not in devices_by_area:
                    devices_by_area[device.area_id] = []
                devices_by_area[device.area_id].append(device.display_name)

        for entity in entities:
            if entity.area_id:
                if entity.area_id not in entities_by_area:
                    entities_by_area[entity.area_id] = []
                entities_by_area[entity.area_id].append(entity.entity_id)

        # Create areas with counts
        result = []
        for area in areas:
            area_devices = devices_by_area.get(area.area_id, [])
            area_entities = entities_by_area.get(area.area_id, [])
            result.append(
                AreaWithCounts.from_area(
                    area,
                    device_count=len(area_devices),
                    entity_count=len(area_entities),
                    devices=area_devices,
                    entities=area_entities,
                )
            )

        return result

    async def get_area(self, area_id: str) -> AreaWithCounts | None:
        """Get a single area with full details.

        Args:
            area_id: Area ID to look up

        Returns:
            Area with counts if found, None otherwise
        """
        areas = await self.list_areas_with_counts()
        for area in areas:
            if area.area_id == area_id or area.name.lower() == area_id.lower():
                return area
        return None

    async def get_area_summary(self) -> dict[str, Any]:
        """Get summary statistics about areas.

        Returns:
            Dictionary with area statistics
        """
        areas = await self.list_areas_with_counts()
        devices = await self.list_devices()
        entities = await self.list_entity_registry()

        # Count devices and entities with/without areas
        devices_with_area = sum(1 for d in devices if d.area_id)
        entities_with_area = sum(1 for e in entities if e.area_id)

        # Find empty areas
        empty_areas = [a for a in areas if a.device_count == 0 and a.entity_count == 0]

        return {
            "total_areas": len(areas),
            "empty_areas": len(empty_areas),
            "total_devices": len(devices),
            "devices_with_area": devices_with_area,
            "devices_without_area": len(devices) - devices_with_area,
            "total_entities": len(entities),
            "entities_with_area": entities_with_area,
            "entities_without_area": len(entities) - entities_with_area,
            "area_coverage_devices": (
                round(devices_with_area / len(devices) * 100, 1)
                if devices
                else 0
            ),
            "area_coverage_entities": (
                round(entities_with_area / len(entities) * 100, 1)
                if entities
                else 0
            ),
        }

    async def check_naming_issues(self) -> list[dict[str, Any]]:
        """Check for area naming issues.

        Returns:
            List of naming issues found
        """
        areas = await self.list_areas()
        issues: list[dict[str, Any]] = []

        # Common naming patterns to check
        common_typos = {
            "garrage": "garage",
            "dinning": "dining",
            "laundrey": "laundry",
            "bathrom": "bathroom",
            "bedrrom": "bedroom",
            "kichen": "kitchen",
            "livng": "living",
        }

        # Check for potential typos
        for area in areas:
            name_lower = area.name.lower()
            for typo, correct in common_typos.items():
                if typo in name_lower:
                    issues.append({
                        "area_id": area.area_id,
                        "area_name": area.name,
                        "issue_type": "possible_typo",
                        "message": (
                            f"'{area.name}' may contain typo "
                            f"'{typo}' -> '{correct}'"
                        ),
                        "suggestion": area.name.replace(typo, correct).replace(
                            typo.capitalize(), correct.capitalize()
                        ),
                    })

        # Check for inconsistent naming (e.g., "Hall" vs "Hallway")
        name_variants: dict[str, list[str]] = {}
        for area in areas:
            # Normalize: remove common suffixes, convert to base form
            base = re.sub(r"(room|way|area)$", "", area.name.lower().strip())
            if base not in name_variants:
                name_variants[base] = []
            name_variants[base].append(area.name)

        # Report areas with similar base names
        for base, names in name_variants.items():
            if len(names) > 1 and base:  # Multiple areas with same base
                issues.append({
                    "area_id": None,
                    "area_name": None,
                    "issue_type": "inconsistent_naming",
                    "message": f"Similar area names found: {', '.join(names)}",
                    "suggestion": "Consider consolidating or using consistent naming",
                })

        # Check for device-like names (not locations)
        device_patterns = [
            r"^(sonos|hue|philips|ikea|shelly|zigbee|zwave|wifi)",
            r"(speaker|bulb|sensor|switch|plug|remote|controller)$",
        ]
        for area in areas:
            for pattern in device_patterns:
                if re.search(pattern, area.name.lower()):
                    issues.append({
                        "area_id": area.area_id,
                        "area_name": area.name,
                        "issue_type": "device_name",
                        "message": (
                            f"'{area.name}' appears to be a device name, not a location"
                        ),
                        "suggestion": "Areas should represent physical locations",
                    })
                    break

        return issues

    async def find_empty_areas(self) -> list[Area]:
        """Find areas with no devices or entities.

        Returns:
            List of empty areas
        """
        areas = await self.list_areas_with_counts()
        return [a for a in areas if a.device_count == 0 and a.entity_count == 0]

    async def get_unassigned_devices(self) -> list[Device]:
        """Get devices not assigned to any area.

        Returns:
            List of devices without area assignment
        """
        devices = await self.list_devices()
        return [d for d in devices if not d.area_id and not d.disabled_by]

    async def get_unassigned_entities(self) -> list[EntityRegistryEntry]:
        """Get entities not assigned to any area (directly or via device).

        Returns:
            List of entities without area assignment
        """
        entities = await self.list_entity_registry()
        devices = await self.list_devices()

        # Build device-to-area map
        device_areas = {d.id: d.area_id for d in devices}

        unassigned = []
        for entity in entities:
            if entity.disabled_by:
                continue
            # Entity has direct area assignment
            if entity.area_id:
                continue
            # Entity's device has area assignment
            if entity.device_id and device_areas.get(entity.device_id):
                continue
            unassigned.append(entity)

        return unassigned
