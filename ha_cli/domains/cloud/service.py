"""Cloud service for interacting with Home Assistant Cloud (Nabu Casa)."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from ...common.client import HAClient
from ...common.exceptions import ConnectionError, WebSocketError

logger = logging.getLogger(__name__)


def _as_bool(value: object, default: bool = False) -> bool:
    """Safely extract a boolean value, returning default if not a bool."""
    return value if isinstance(value, bool) else default


def _as_str(value: object) -> str | None:
    """Safely extract a string value, returning None if not a non-empty string."""
    return value if isinstance(value, str) and value else None


def _as_str_list(value: object) -> list[str]:
    """Safely extract a list of non-empty strings, filtering invalid items."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


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

        # Count only valid non-empty strings in include_entities
        alexa_entity_count = len(_as_str_list(alexa_entities.get("include_entities")))

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

    async def _get_entity_registry_exposure(self) -> dict[str, bool]:
        """Get Alexa exposure status from entity registry.

        Returns a mapping of entity_id -> should_expose from the entity registry.
        The cloud/alexa/entities API doesn't include exposure status, so we need
        to fetch it from the entity registry where it's stored under
        options['cloud.alexa']['should_expose'].
        """
        try:
            registry = await self.client._ws_call("config/entity_registry/list")
            if not isinstance(registry, list):
                logger.warning("Entity registry returned unexpected type: %s", type(registry).__name__)
                return {}

            exposure_map: dict[str, bool] = {}
            for entry in registry:
                if not isinstance(entry, dict):
                    continue
                entity_id = entry.get("entity_id")
                if not entity_id or not isinstance(entity_id, str):
                    continue

                # Extract exposure from options['cloud.alexa']['should_expose']
                options = entry.get("options", {})
                if not isinstance(options, dict):
                    continue
                alexa_opts = options.get("cloud.alexa", {})
                if not isinstance(alexa_opts, dict):
                    continue
                should_expose = alexa_opts.get("should_expose")
                if isinstance(should_expose, bool):
                    exposure_map[entity_id] = should_expose

            return exposure_map
        except (WebSocketError, ConnectionError) as e:
            logger.warning("Failed to fetch entity registry for exposure status: %s", e)
            return {}

    async def get_alexa_entities(self) -> list[AlexaEntity]:
        """Get all Alexa-compatible entities with exposure status.

        Uses WebSocket commands:
        - cloud/alexa/entities: Get Alexa-compatible entities and their categories
        - config/entity_registry/list: Get exposure status from entity registry

        Note: The cloud/alexa/entities API doesn't include should_expose, so we
        join with the entity registry to get accurate exposure status.
        """
        # Fetch both API responses concurrently for better performance
        result, exposure_map = await asyncio.gather(
            self.client._ws_call("cloud/alexa/entities"),
            self._get_entity_registry_exposure(),
        )

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

            # Normalize display_categories to list of non-empty strings
            raw_categories = item.get("display_categories", [])
            categories = (
                [raw_categories]
                if isinstance(raw_categories, str) and raw_categories
                else _as_str_list(raw_categories)
            )

            # Get exposure from registry, fall back to API response, then False
            should_expose = exposure_map.get(
                entity_id,
                _as_bool(item.get("should_expose"), False)
            )

            entities.append(
                AlexaEntity(
                    entity_id=entity_id,
                    should_expose=should_expose,
                    display_categories=categories,
                )
            )

        if skipped_count > 0:
            logger.debug("Skipped %d malformed entries in cloud/alexa/entities response", skipped_count)

        # Sort by entity_id for deterministic output
        entities.sort(key=lambda e: e.entity_id)
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

    async def set_entity_exposure(self, entity_id: str, expose: bool) -> dict[str, Any]:
        """Set Alexa exposure for a single entity.

        Uses WebSocket command: config/entity_registry/update
        with options_domain='cloud.alexa' and options={'should_expose': expose}

        Args:
            entity_id: The entity to modify (e.g., 'light.lounge')
            expose: True to expose to Alexa, False to hide

        Returns:
            The updated entity registry entry

        Raises:
            NotFoundError: If entity_id doesn't exist in the registry
            WebSocketError: If update fails
        """
        from ...common.exceptions import NotFoundError

        try:
            result = await self.client._ws_call(
                "config/entity_registry/update",
                entity_id=entity_id,
                options_domain="cloud.alexa",
                options={"should_expose": expose},
            )
        except WebSocketError as e:
            # Convert "not_found" errors to NotFoundError for better handling
            error_msg = str(e).lower()
            if "not_found" in error_msg or "not found" in error_msg:
                raise NotFoundError(f"Entity not found: {entity_id}") from e
            raise

        if not isinstance(result, dict):
            raise WebSocketError(
                f"Unexpected response type: {type(result).__name__}"
            )

        return result

    async def set_entities_exposure(
        self, entity_ids: list[str], expose: bool
    ) -> tuple[list[str], list[tuple[str, str]]]:
        """Set Alexa exposure for multiple entities.

        Args:
            entity_ids: List of entity IDs to modify
            expose: True to expose to Alexa, False to hide

        Returns:
            Tuple of (successful_ids, failed_ids_with_errors)
            - successful_ids: List of entity IDs that were updated
            - failed_ids_with_errors: List of (entity_id, error_message) tuples
        """
        from ...common.exceptions import NotFoundError

        successful: list[str] = []
        failed: list[tuple[str, str]] = []

        for entity_id in entity_ids:
            try:
                await self.set_entity_exposure(entity_id, expose)
                successful.append(entity_id)
            except (NotFoundError, WebSocketError) as e:
                failed.append((entity_id, str(e)))

        return successful, failed
