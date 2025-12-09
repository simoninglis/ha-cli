"""Data models for areas domain."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Area:
    """Home Assistant area model."""

    area_id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    floor_id: str | None = None
    icon: str | None = None
    labels: list[str] = field(default_factory=list)
    picture: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Area":
        """Create Area from dictionary."""
        return cls(
            area_id=data.get("area_id", ""),
            name=data.get("name", ""),
            aliases=data.get("aliases", []),
            floor_id=data.get("floor_id"),
            icon=data.get("icon"),
            labels=data.get("labels", []),
            picture=data.get("picture"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "area_id": self.area_id,
            "name": self.name,
        }
        if self.aliases:
            result["aliases"] = self.aliases
        if self.floor_id:
            result["floor_id"] = self.floor_id
        if self.icon:
            result["icon"] = self.icon
        if self.labels:
            result["labels"] = self.labels
        if self.picture:
            result["picture"] = self.picture
        return result


@dataclass
class AreaWithCounts(Area):
    """Area with device and entity counts."""

    device_count: int = 0
    entity_count: int = 0
    devices: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)

    @classmethod
    def from_area(
        cls,
        area: Area,
        device_count: int = 0,
        entity_count: int = 0,
        devices: list[str] | None = None,
        entities: list[str] | None = None,
    ) -> "AreaWithCounts":
        """Create AreaWithCounts from an Area."""
        return cls(
            area_id=area.area_id,
            name=area.name,
            aliases=area.aliases,
            floor_id=area.floor_id,
            icon=area.icon,
            labels=area.labels,
            picture=area.picture,
            device_count=device_count,
            entity_count=entity_count,
            devices=devices or [],
            entities=entities or [],
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict()
        result["device_count"] = self.device_count
        result["entity_count"] = self.entity_count
        if self.devices:
            result["devices"] = self.devices
        if self.entities:
            result["entities"] = self.entities
        return result


@dataclass
class Device:
    """Home Assistant device model."""

    id: str
    name: str | None = None
    name_by_user: str | None = None
    area_id: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    sw_version: str | None = None
    hw_version: str | None = None
    disabled_by: str | None = None
    config_entries: list[str] = field(default_factory=list)
    identifiers: list[list[str]] = field(default_factory=list)
    connections: list[list[str]] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Device":
        """Create Device from dictionary."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name"),
            name_by_user=data.get("name_by_user"),
            area_id=data.get("area_id"),
            manufacturer=data.get("manufacturer"),
            model=data.get("model"),
            sw_version=data.get("sw_version"),
            hw_version=data.get("hw_version"),
            disabled_by=data.get("disabled_by"),
            config_entries=data.get("config_entries", []),
            identifiers=data.get("identifiers", []),
            connections=data.get("connections", []),
            labels=data.get("labels", []),
        )

    @property
    def display_name(self) -> str:
        """Get display name (user-defined or device name)."""
        return self.name_by_user or self.name or self.id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.display_name,
        }
        if self.area_id:
            result["area_id"] = self.area_id
        if self.manufacturer:
            result["manufacturer"] = self.manufacturer
        if self.model:
            result["model"] = self.model
        if self.sw_version:
            result["sw_version"] = self.sw_version
        if self.disabled_by:
            result["disabled_by"] = self.disabled_by
        if self.labels:
            result["labels"] = self.labels
        return result


@dataclass
class Floor:
    """Home Assistant floor model."""

    floor_id: str
    name: str
    level: int = 0
    aliases: list[str] = field(default_factory=list)
    icon: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Floor":
        """Create Floor from dictionary."""
        return cls(
            floor_id=data.get("floor_id", ""),
            name=data.get("name", ""),
            level=data.get("level", 0),
            aliases=data.get("aliases", []),
            icon=data.get("icon"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "floor_id": self.floor_id,
            "name": self.name,
            "level": self.level,
        }
        if self.aliases:
            result["aliases"] = self.aliases
        if self.icon:
            result["icon"] = self.icon
        return result


@dataclass
class Label:
    """Home Assistant label model."""

    label_id: str
    name: str
    color: str | None = None
    description: str | None = None
    icon: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Label":
        """Create Label from dictionary."""
        return cls(
            label_id=data.get("label_id", ""),
            name=data.get("name", ""),
            color=data.get("color"),
            description=data.get("description"),
            icon=data.get("icon"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "label_id": self.label_id,
            "name": self.name,
        }
        if self.color:
            result["color"] = self.color
        if self.description:
            result["description"] = self.description
        if self.icon:
            result["icon"] = self.icon
        return result


@dataclass
class EntityRegistryEntry:
    """Home Assistant entity registry entry."""

    entity_id: str
    unique_id: str
    platform: str
    area_id: str | None = None
    device_id: str | None = None
    disabled_by: str | None = None
    name: str | None = None
    icon: str | None = None
    labels: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EntityRegistryEntry":
        """Create EntityRegistryEntry from dictionary."""
        return cls(
            entity_id=data.get("entity_id", ""),
            unique_id=data.get("unique_id", ""),
            platform=data.get("platform", ""),
            area_id=data.get("area_id"),
            device_id=data.get("device_id"),
            disabled_by=data.get("disabled_by"),
            name=data.get("name"),
            icon=data.get("icon"),
            labels=data.get("labels", []),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "entity_id": self.entity_id,
            "platform": self.platform,
        }
        if self.area_id:
            result["area_id"] = self.area_id
        if self.device_id:
            result["device_id"] = self.device_id
        if self.name:
            result["name"] = self.name
        if self.disabled_by:
            result["disabled_by"] = self.disabled_by
        if self.labels:
            result["labels"] = self.labels
        return result
