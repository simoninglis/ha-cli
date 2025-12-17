"""Cloud service for interacting with Home Assistant Cloud (Nabu Casa)."""

from dataclasses import dataclass
from typing import Any

from ...common.client import HAClient
from ...common.exceptions import WebSocketError


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

        # Handle not logged in case
        if not result.get("logged_in", False):
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

        prefs = result.get("prefs", {})
        alexa_entities = result.get("alexa_entities", {})
        alexa_entity_count = len(alexa_entities.get("include_entities", []))

        return CloudStatus(
            logged_in=result.get("logged_in", False),
            cloud_connected=result.get("cloud", "disconnected") == "connected",
            remote_enabled=prefs.get("remote_enabled", False),
            remote_connected=result.get("remote_connected", False),
            alexa_enabled=prefs.get("alexa_enabled", False),
            alexa_registered=result.get("alexa_registered", False),
            google_enabled=prefs.get("google_enabled", False),
            google_registered=result.get("google_registered", False),
            email=result.get("email"),
            subscription_expiration=result.get("subscription_expiration"),
            remote_domain=result.get("remote_domain"),
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
        for item in result:
            if not isinstance(item, dict):
                continue  # Skip malformed entries
            entities.append(
                AlexaEntity(
                    entity_id=item.get("entity_id", ""),
                    should_expose=item.get("should_expose", False),
                    display_categories=item.get("display_categories", []),
                )
            )

        return entities

    async def sync_alexa(self) -> dict[str, Any]:
        """Trigger Alexa device synchronization.

        Uses WebSocket command: cloud/alexa/sync
        This tells Alexa to rediscover devices from Home Assistant.
        """
        result = await self.client._ws_call("cloud/alexa/sync")
        return result if isinstance(result, dict) else {}
