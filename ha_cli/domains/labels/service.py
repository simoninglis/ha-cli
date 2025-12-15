"""Labels service for Home Assistant label registry operations.

Uses HAClient for WebSocket communication with Home Assistant.
Follows the same patterns as the areas domain.
"""

from dataclasses import dataclass
from typing import Any, Literal, cast

from ...common.client import HAClient
from ...common.exceptions import NotFoundError, WebSocketError

# Type alias for label operation status
LabelAssignStatus = Literal["assigned", "already_assigned"]
LabelRemoveStatus = Literal["removed", "not_present"]


@dataclass
class Label:
    """Represents a Home Assistant label."""

    label_id: str
    name: str
    icon: str | None = None
    color: str | None = None
    description: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Label":
        """Create Label from dictionary.

        Handles None values from HA by coercing to empty string for required fields.
        """
        return cls(
            label_id=data.get("label_id") or "",
            name=data.get("name") or "",
            icon=data.get("icon"),
            color=data.get("color"),
            description=data.get("description"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "label_id": self.label_id,
            "name": self.name,
            "icon": self.icon,
            "color": self.color,
            "description": self.description,
        }


class LabelsService:
    """Service for interacting with Home Assistant label registry.

    Note: Label assignment operations (assign/remove) use read-modify-write
    pattern which is non-atomic. Concurrent modifications may be overwritten.
    """

    def __init__(self, client: HAClient) -> None:
        """Initialize labels service.

        Args:
            client: Home Assistant client
        """
        self.client = client

    async def list_labels(self) -> list[Label]:
        """List all labels in the registry.

        Returns:
            List of Label objects sorted by name
        """
        result = await self.client._ws_call("config/label_registry/list")
        result_list = cast(list[dict[str, Any]], result)
        labels = [Label.from_dict(item) for item in result_list]
        return sorted(labels, key=lambda label: label.name.lower())

    async def get_label(self, label_id: str) -> Label | None:
        """Get a specific label by ID.

        Args:
            label_id: The label ID to find

        Returns:
            Label object if found, None otherwise
        """
        labels = await self.list_labels()
        for label in labels:
            if label.label_id == label_id:
                return label
        return None

    async def create_label(
        self,
        name: str,
        icon: str | None = None,
        color: str | None = None,
        description: str | None = None,
    ) -> Label:
        """Create a new label.

        Args:
            name: Label name (Home Assistant generates the label_id)
            icon: MDI icon (e.g., "mdi:lightbulb-group")
            color: Color name (e.g., "orange", "blue")
            description: Optional description

        Returns:
            Created Label object

        Raises:
            WebSocketError: If creation fails (e.g., duplicate name)
        """
        kwargs: dict[str, Any] = {"name": name}
        if icon:
            kwargs["icon"] = icon
        if color:
            kwargs["color"] = color
        if description:
            kwargs["description"] = description

        result = await self.client._ws_call("config/label_registry/create", **kwargs)
        return Label.from_dict(result)

    async def delete_label(self, label_id: str, skip_check: bool = False) -> bool:
        """Delete a label.

        Args:
            label_id: The label ID to delete
            skip_check: If True, skip existence check (use when caller already verified)

        Returns:
            True if deleted successfully

        Raises:
            NotFoundError: If label doesn't exist (when skip_check=False)
        """
        if not skip_check:
            # Verify label exists first
            label = await self.get_label(label_id)
            if not label:
                raise NotFoundError(f"Label not found: {label_id}")

        await self.client._ws_call("config/label_registry/delete", label_id=label_id)
        return True

    async def get_entity_labels(self, entity_id: str) -> list[str]:
        """Get labels assigned to an entity.

        Args:
            entity_id: The entity ID to check

        Returns:
            List of label IDs assigned to the entity

        Raises:
            NotFoundError: If entity doesn't exist in registry
        """
        try:
            result = await self.client._ws_call(
                "config/entity_registry/get", entity_id=entity_id
            )
        except WebSocketError as e:
            # Translate WebSocket "not_found" errors to NotFoundError
            # Check e.details first (structured), then fall back to string matching
            error_code = e.details.get("code", "") if e.details else ""
            if error_code == "not_found" or "not_found" in str(e).lower():
                raise NotFoundError(f"Entity not found in registry: {entity_id}") from e
            raise

        if not result:
            raise NotFoundError(f"Entity not found in registry: {entity_id}")

        # Handle case where labels key exists but is None
        labels: list[str] = result.get("labels") or []
        return labels

    async def assign_label(self, entity_id: str, label_id: str) -> LabelAssignStatus:
        """Assign a label to an entity.

        Note: This uses read-modify-write which is non-atomic.
        Concurrent modifications may be overwritten.

        Args:
            entity_id: The entity ID
            label_id: The label ID to assign

        Returns:
            Status indicating if the label was newly assigned or already present

        Raises:
            NotFoundError: If entity or label doesn't exist
        """
        # Verify label exists
        label = await self.get_label(label_id)
        if not label:
            raise NotFoundError(f"Label not found: {label_id}")

        # Get current labels
        current_labels = await self.get_entity_labels(entity_id)

        # Check if already assigned
        if label_id in current_labels:
            return "already_assigned"

        # Add new label
        new_labels = current_labels + [label_id]

        await self.client._ws_call(
            "config/entity_registry/update",
            entity_id=entity_id,
            labels=new_labels,
        )
        return "assigned"

    async def remove_label(self, entity_id: str, label_id: str) -> LabelRemoveStatus:
        """Remove a label from an entity.

        Note: This uses read-modify-write which is non-atomic.
        Concurrent modifications may be overwritten.

        Args:
            entity_id: The entity ID
            label_id: The label ID to remove

        Returns:
            Status indicating if the label was removed or wasn't present

        Raises:
            NotFoundError: If entity or label doesn't exist in registry
        """
        # Verify label exists (prevents typos from silently succeeding)
        label = await self.get_label(label_id)
        if not label:
            raise NotFoundError(f"Label not found: {label_id}")

        # Get current labels
        current_labels = await self.get_entity_labels(entity_id)

        # Check if not assigned
        if label_id not in current_labels:
            return "not_present"

        # Remove label
        new_labels = [lbl for lbl in current_labels if lbl != label_id]

        await self.client._ws_call(
            "config/entity_registry/update",
            entity_id=entity_id,
            labels=new_labels,
        )
        return "removed"

    async def list_entities_with_label(self, label_id: str) -> list[str]:
        """List all entities with a specific label.

        Uses entity registry list instead of render_template to avoid
        template injection risks and parsing issues.

        Args:
            label_id: The label ID to search for

        Returns:
            Sorted list of entity IDs with the label
        """
        result = await self.client._ws_call("config/entity_registry/list")
        result_list = cast(list[dict[str, Any]], result)

        entities = [
            entity_id
            for entry in result_list
            if label_id in (entry.get("labels") or [])
            and (entity_id := entry.get("entity_id"))
        ]
        return sorted(entities)
