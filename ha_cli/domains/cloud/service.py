"""Cloud service for interacting with Home Assistant Cloud (Nabu Casa)."""

import logging
from dataclasses import dataclass
from typing import Any

from ...common.client import HAClient
from ...common.exceptions import WebSocketError

logger = logging.getLogger(__name__)


def _as_bool(value: object, default: bool = False) -> bool:
    """Safely extract a boolean value, returning default if not a bool."""
    return value if isinstance(value, bool) else default


def _as_str(value: object) -> str | None:
    """Safely extract a string value, returning None if not a non-empty string."""
    return value if isinstance(value, str) and value else None


@dataclass
class CloudStatus:
    """Cloud connection status."""

    logged_in: bool
    cloud_connected: bool
    remote_enabled: bool
    remote_connected: bool
    alexa_enabled: bool
    alexa_registered: bool
    google_enabled: bool
    google_registered: bool
    email: str | None = None
    subscription_expiration: str | None = None
    remote_domain: str | None = None
    alexa_entity_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "logged_in": self.logged_in,
            "cloud_connected": self.cloud_connected,
            "remote_enabled": self.remote_enabled,
            "remote_connected": self.remote_connected,
            "alexa_enabled": self.alexa_enabled,
            "alexa_registered": self.alexa_registered,
            "alexa_entity_count": self.alexa_entity_count,
            "google_enabled": self.google_enabled,
            "google_registered": self.google_registered,
            "email": self.email,
            "subscription_expiration": self.subscription_expiration,
            "remote_domain": self.remote_domain,
        }


@dataclass
class AlexaEntity:
    """Alexa entity configuration."""

    entity_id: str
    should_expose: bool
    display_categories: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_id": self.entity_id,
            "should_expose": self.should_expose,
            "display_categories": self.display_categories,
        }


class CloudService:
    """Service for cloud operations."""

    def __init__(self, client: HAClient):
        """Initialize the service."""
        self.client = client

    async def get_status(self) -> CloudStatus:
        """Get cloud connection status.

        Uses WebSocket command: cloud/status
        """
        result = await self.client._ws_call("cloud/status")

        # Validate result type
        if not isinstance(result, dict):
            raise WebSocketError(f"Unexpected cloud/status response type: {type(result).__name__}")

        # Handle not logged in case (validate as bool, don't trust truthy strings)
        logged_in = _as_bool(result.get("logged_in"), False)
        if not logged_in:
            return CloudStatus(
                logged_in=False,
                cloud_connected=False,
                remote_enabled=False,
                remote_connected=False,
                alexa_enabled=False,
                alexa_registered=False,
                google_enabled=False,
                google_registered=False,
            )

        # Defensively validate nested structures
        prefs = result.get("prefs", {})
        if not isinstance(prefs, dict):
            prefs = {}

        alexa_entities = result.get("alexa_entities", {})
        if not isinstance(alexa_entities, dict):
            alexa_entities = {}

        include_entities = alexa_entities.get("include_entities", [])
        if not isinstance(include_entities, list):
            include_entities = []
        # Count only valid non-empty strings
        alexa_entity_count = sum(1 for e in include_entities if isinstance(e, str) and e)

        # Parse cloud connection status (handles both bool and string)
        cloud_val = result.get("cloud")
        cloud_connected = cloud_val is True or cloud_val == "connected"

        return CloudStatus(
            logged_in=logged_in,
            cloud_connected=cloud_connected,
            remote_enabled=_as_bool(prefs.get("remote_enabled"), False),
            remote_connected=_as_bool(result.get("remote_connected"), False),
            alexa_enabled=_as_bool(prefs.get("alexa_enabled"), False),
            alexa_registered=_as_bool(result.get("alexa_registered"), False),
            google_enabled=_as_bool(prefs.get("google_enabled"), False),
            google_registered=_as_bool(result.get("google_registered"), False),
            email=_as_str(result.get("email")),
            subscription_expiration=_as_str(result.get("subscription_expiration")),
            remote_domain=_as_str(result.get("remote_domain")),
            alexa_entity_count=alexa_entity_count,
        )

    async def get_alexa_entities(self) -> list[AlexaEntity]:
        """Get all Alexa-compatible entities.

        Uses WebSocket command: cloud/alexa/entities
        """
        result = await self.client._ws_call("cloud/alexa/entities")

        # Validate result type
        if not isinstance(result, list):
            raise WebSocketError(f"Unexpected cloud/alexa/entities response type: {type(result).__name__}")

        entities = []
        skipped_count = 0

        for item in result:
            if not isinstance(item, dict):
                skipped_count += 1
                continue  # Skip malformed entries

            # Validate entity_id is present and non-empty
            entity_id = item.get("entity_id", "")
            if not entity_id or not isinstance(entity_id, str):
                skipped_count += 1
                continue  # Skip entries without valid entity_id

            # Normalize display_categories to list of strings (only accept actual strings)
            raw_categories = item.get("display_categories", [])
            if isinstance(raw_categories, list):
                categories = [c for c in raw_categories if isinstance(c, str) and c]
            elif isinstance(raw_categories, str) and raw_categories:
                categories = [raw_categories]
            else:
                categories = []

            entities.append(
                AlexaEntity(
                    entity_id=entity_id,
                    should_expose=_as_bool(item.get("should_expose"), False),
                    display_categories=categories,
                )
            )

        if skipped_count > 0:
            logger.debug("Skipped %d malformed entries in cloud/alexa/entities response", skipped_count)

        return entities

    async def sync_alexa(self) -> dict[str, Any]:
        """Trigger Alexa device synchronization.

        Uses WebSocket command: cloud/alexa/sync
        This tells Alexa to rediscover devices from Home Assistant.

        Raises:
            WebSocketError: If sync fails or returns unexpected response type.
        """
        result = await self.client._ws_call("cloud/alexa/sync")

        # Validate result type - sync should return a dict or None on success
        if result is None:
            return {}  # Successful sync with no additional data
        if not isinstance(result, dict):
            raise WebSocketError(
                f"Unexpected cloud/alexa/sync response type: {type(result).__name__}"
            )
        return result
