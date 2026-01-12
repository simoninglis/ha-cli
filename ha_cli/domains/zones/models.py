"""Data models for zones domain."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Zone:
    """Home Assistant zone model.

    Zones define geographic regions for presence detection via the Companion App.
    """

    zone_id: str
    name: str
    latitude: float
    longitude: float
    radius: float = 100.0
    icon: str | None = None
    passive: bool = False
    persons: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Zone":
        """Create Zone from dictionary.

        Args:
            data: Dictionary from Home Assistant API

        Returns:
            Zone instance
        """
        return cls(
            zone_id=data.get("id", ""),
            name=data.get("name", ""),
            latitude=data.get("latitude", 0.0),
            longitude=data.get("longitude", 0.0),
            radius=data.get("radius", 100.0),
            icon=data.get("icon"),
            passive=data.get("passive", False),
            persons=data.get("persons", []),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        result: dict[str, Any] = {
            "zone_id": self.zone_id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius": self.radius,
            "passive": self.passive,
        }
        if self.icon:
            result["icon"] = self.icon
        if self.persons:
            result["persons"] = self.persons
        return result

    @property
    def entity_id(self) -> str:
        """Get the zone entity ID.

        Returns:
            Entity ID in format zone.<zone_id>
        """
        return f"zone.{self.zone_id}"

    @property
    def google_maps_url(self) -> str:
        """Get Google Maps URL for this zone.

        Returns:
            Google Maps URL centered on zone location
        """
        return f"https://maps.google.com/?q={self.latitude},{self.longitude}"
