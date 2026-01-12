"""Service layer for zones domain."""

import logging
from typing import Any, cast

from ...common.client import HAClient
from ...common.exceptions import NotFoundError, ValidationError
from .models import Zone

logger = logging.getLogger(__name__)


class ZoneService:
    """Service for managing Home Assistant zones.

    Zones define geographic regions for presence detection via the Companion App.
    The "home" zone is special and cannot be deleted.
    """

    def __init__(self, client: HAClient) -> None:
        """Initialize zone service.

        Args:
            client: Home Assistant client
        """
        self.client = client

    async def list_zones(self) -> list[Zone]:
        """Get all zones from the zone registry.

        Returns:
            List of zones sorted by name
        """
        result = await self.client._ws_call("zone/list")
        result_list = cast(list[dict[str, Any]], result)
        zones = []
        for item in result_list:
            zones.append(Zone.from_dict(item))
        return sorted(zones, key=lambda z: z.name.lower())

    async def get_zone(self, zone_id: str) -> Zone | None:
        """Get a specific zone by ID or name.

        Args:
            zone_id: Zone ID or name to look up

        Returns:
            Zone if found, None otherwise
        """
        zones = await self.list_zones()
        for zone in zones:
            if zone.zone_id == zone_id or zone.name.lower() == zone_id.lower():
                return zone
        return None

    async def create_zone(
        self,
        name: str,
        latitude: float,
        longitude: float,
        radius: float = 100.0,
        icon: str | None = None,
        passive: bool = False,
    ) -> Zone:
        """Create a new zone.

        Args:
            name: Zone name (required)
            latitude: Center point latitude (required)
            longitude: Center point longitude (required)
            radius: Radius in meters (default: 100)
            icon: Optional icon (e.g., "mdi:school")
            passive: Hide from UI and device tracker (default: False)

        Returns:
            The created Zone

        Raises:
            ValidationError: If zone with same name already exists or invalid params
        """
        payload: dict[str, Any] = {
            "name": name,
            "latitude": latitude,
            "longitude": longitude,
            "radius": radius,
            "passive": passive,
        }
        if icon is not None:
            payload["icon"] = icon

        try:
            result = await self.client._ws_call(
                "zone/create", **payload
            )
            result_dict = cast(dict[str, Any], result)
            return Zone.from_dict(result_dict)
        except Exception as e:
            error_msg = str(e).lower()
            if "already exists" in error_msg or "name is already in use" in error_msg:
                raise ValidationError(f"Zone with name '{name}' already exists") from e
            if "invalid" in error_msg:
                raise ValidationError(f"Invalid zone parameters: {e}") from e
            raise

    async def update_zone(
        self,
        zone_id: str,
        name: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        radius: float | None = None,
        icon: str | None = None,
        passive: bool | None = None,
    ) -> Zone:
        """Update an existing zone.

        Args:
            zone_id: Zone ID to update (required)
            name: New zone name (optional)
            latitude: New latitude (optional)
            longitude: New longitude (optional)
            radius: New radius in meters (optional)
            icon: New icon (optional, use "" to clear)
            passive: New passive state (optional)

        Returns:
            The updated Zone

        Raises:
            NotFoundError: If zone not found
            ValidationError: If name already used or invalid parameters
        """
        # Build request payload - only include fields that were specified
        payload: dict[str, Any] = {"zone_id": zone_id}
        if name is not None:
            payload["name"] = name
        if latitude is not None:
            payload["latitude"] = latitude
        if longitude is not None:
            payload["longitude"] = longitude
        if radius is not None:
            payload["radius"] = radius
        if icon is not None:
            # Empty string means clear the value
            payload["icon"] = icon if icon else None
        if passive is not None:
            payload["passive"] = passive

        try:
            result = await self.client._ws_call(
                "zone/update", **payload
            )
            result_dict = cast(dict[str, Any], result)
            return Zone.from_dict(result_dict)
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "unknown zone" in error_msg:
                raise NotFoundError(f"Zone not found: {zone_id}") from e
            if "already exists" in error_msg or "name is already in use" in error_msg:
                raise ValidationError(f"Zone name '{name}' is already in use") from e
            if "invalid" in error_msg:
                raise ValidationError(f"Invalid zone parameters: {e}") from e
            raise

    async def delete_zone(self, zone_id: str) -> None:
        """Delete a zone.

        The "home" zone cannot be deleted.

        Args:
            zone_id: Zone ID to delete

        Raises:
            NotFoundError: If zone not found
            ValidationError: If trying to delete the "home" zone
        """
        # Check for home zone
        if zone_id == "home":
            raise ValidationError("Cannot delete the 'home' zone")

        try:
            await self.client._ws_call(
                "zone/delete", zone_id=zone_id
            )
        except Exception as e:
            error_msg = str(e).lower()
            if "not found" in error_msg or "unknown zone" in error_msg:
                raise NotFoundError(f"Zone not found: {zone_id}") from e
            if "home" in error_msg or "cannot delete" in error_msg:
                raise ValidationError("Cannot delete the 'home' zone") from e
            raise

    async def get_zone_summary(self) -> dict[str, Any]:
        """Get summary statistics about zones.

        Returns:
            Dictionary with zone statistics
        """
        zones = await self.list_zones()

        # Count passive vs active zones
        passive_count = sum(1 for z in zones if z.passive)
        active_count = len(zones) - passive_count

        # Check for home zone
        has_home = any(z.zone_id == "home" for z in zones)

        return {
            "total_zones": len(zones),
            "active_zones": active_count,
            "passive_zones": passive_count,
            "has_home_zone": has_home,
        }
