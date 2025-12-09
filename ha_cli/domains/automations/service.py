"""Service layer for Home Assistant automation management."""

import logging
from pathlib import Path
from typing import Any

import yaml

from ...common.client import HAClient
from ...common.exceptions import AutomationNotFoundError, ValidationError
from .models import Automation, AutomationListResponse

logger = logging.getLogger(__name__)


class AutomationCRUD:
    """Service for CRUD operations on automations.

    This service provides automation management with REST API support for
    create/update/delete operations. The REST API requires the 'config'
    integration to be enabled in Home Assistant.

    The service automatically detects REST API availability and falls back
    to graceful error handling when unavailable.
    """

    def __init__(self, client: HAClient) -> None:
        """Initialize service with HAClient."""
        self.client = client
        self._rest_api_available: bool | None = None

    async def _check_rest_api(self) -> bool:
        """Check if REST API is available (cached).

        Returns:
            True if REST API is available
        """
        if self._rest_api_available is None:
            self._rest_api_available = await self.client.probe_automation_rest_api()
            if self._rest_api_available:
                logger.info("REST API available for automation CRUD operations")
            else:
                logger.warning(
                    "REST API not available. Create/update/delete operations require "
                    "the 'config' integration to be enabled in Home Assistant."
                )
        return self._rest_api_available

    def _load_automation_file(self, file_path: str) -> dict[str, Any]:
        """Load automation configuration from a YAML or JSON file.

        Args:
            file_path: Path to the configuration file

        Returns:
            Automation configuration dictionary

        Raises:
            ValidationError: If file cannot be read or parsed
        """
        path = Path(file_path)
        if not path.exists():
            raise ValidationError(f"File not found: {file_path}")

        try:
            with open(path) as f:
                content = f.read()

            if path.suffix.lower() in (".yaml", ".yml"):
                config = yaml.safe_load(content)
            elif path.suffix.lower() == ".json":
                import json
                config = json.loads(content)
            else:
                # Try YAML first, then JSON
                try:
                    config = yaml.safe_load(content)
                except yaml.YAMLError:
                    import json
                    config = json.loads(content)

            if not isinstance(config, dict):
                raise ValidationError(f"Invalid automation config: expected dict, got {type(config).__name__}")

            return config
        except (yaml.YAMLError, ValueError) as e:
            raise ValidationError(f"Failed to parse {file_path}: {e}") from e
        except OSError as e:
            raise ValidationError(f"Failed to read {file_path}: {e}") from e
    
    async def list_automations(self, json_output: bool = False, use_websocket: bool = False) -> list[Automation] | list[dict[str, Any]]:
        """List all automations via WebSocket.

        Args:
            json_output: Return raw JSON instead of Automation objects
            use_websocket: Ignored (always uses WebSocket)

        Returns:
            List of automations
        """
        # Always use WebSocket - REST API is undocumented and unreliable
        raw_data = await self._list_automations_websocket()

        if json_output:
            return raw_data

        # Parse response
        response = AutomationListResponse(result=raw_data)
        return response.to_automations()
    
    async def _list_automations_websocket(self) -> list[dict[str, Any]]:
        """List automations via WebSocket (limited info)."""
        states = await self.client.get_automation_states()
        
        # Convert entity states to automation format
        automations = []
        for state in states:
            entity_id = state.get("entity_id", "")
            automation_id = entity_id.replace("automation.", "")
            attributes = state.get("attributes", {})
            
            # Create minimal automation object
            automation = {
                "id": automation_id,
                "alias": attributes.get("friendly_name", automation_id),
                "mode": attributes.get("mode", "single"),
                "enabled": state.get("state") == "on",
                "last_triggered": attributes.get("last_triggered"),
                # WebSocket doesn't provide full config
                "description": "Full configuration not available via WebSocket",
                "trigger": [],
                "condition": [],
                "action": []
            }
            automations.append(automation)
        
        return automations
    
    async def get_automation(self, automation_id: str) -> Automation:
        """Get single automation by ID.

        Args:
            automation_id: Automation ID

        Returns:
            Automation object

        Raises:
            AutomationNotFoundError: If not found
        """
        try:
            data = await self.client.get_automation(automation_id)
            return Automation(**data)
        except Exception as e:
            if "not_found" in str(e).lower() or "not found" in str(e).lower():
                raise AutomationNotFoundError(automation_id) from e
            raise
    
    async def create_automation(self, file_path: str, dry_run: bool = False) -> str:
        """Create automation from file.

        Requires the 'config' integration to be enabled in Home Assistant.

        Args:
            file_path: Path to YAML/JSON file with automation configuration
            dry_run: If True, validate but don't create

        Returns:
            The numeric ID of the created automation

        Raises:
            ValidationError: If file is invalid or REST API unavailable
        """
        # Check REST API availability
        if not await self._check_rest_api():
            raise ValidationError(
                "REST API not available. Creating automations requires the 'config' "
                "integration to be enabled in Home Assistant's configuration.yaml. "
                "Add 'config:' to your configuration and restart Home Assistant."
            )

        # Load and validate the configuration
        config = self._load_automation_file(file_path)

        # Basic validation
        if "trigger" not in config and "triggers" not in config:
            raise ValidationError("Automation must have 'trigger' or 'triggers'")
        if "action" not in config and "actions" not in config:
            raise ValidationError("Automation must have 'action' or 'actions'")

        if dry_run:
            logger.info(f"Dry run: would create automation with alias '{config.get('alias', 'unnamed')}'")
            return "DRY_RUN"

        # Create the automation
        numeric_id = await self.client.create_automation_rest(config)
        logger.info(f"Created automation with ID: {numeric_id}")
        return numeric_id

    async def update_automation(self, automation_id: str, file_path: str, dry_run: bool = False) -> None:
        """Update automation from file.

        Requires the 'config' integration to be enabled in Home Assistant.

        Args:
            automation_id: Automation ID (entity ID or numeric ID)
            file_path: Path to YAML/JSON file with updated configuration
            dry_run: If True, validate but don't update

        Raises:
            ValidationError: If file is invalid or REST API unavailable
            AutomationNotFoundError: If automation not found
        """
        # Check REST API availability
        if not await self._check_rest_api():
            raise ValidationError(
                "REST API not available. Updating automations requires the 'config' "
                "integration to be enabled in Home Assistant's configuration.yaml."
            )

        # Resolve to numeric ID if needed
        if not automation_id.isdigit():
            numeric_id = await self.client.get_automation_numeric_id(automation_id)
            if not numeric_id:
                raise AutomationNotFoundError(automation_id)
            logger.debug(f"Resolved {automation_id} to numeric ID {numeric_id}")
        else:
            numeric_id = automation_id

        # Load and validate the configuration
        config = self._load_automation_file(file_path)

        if dry_run:
            logger.info(f"Dry run: would update automation {automation_id}")
            return

        # Update the automation
        await self.client.update_automation_rest(numeric_id, config)
        logger.info(f"Updated automation {automation_id} (numeric ID: {numeric_id})")

    async def delete_automation(self, automation_id: str, dry_run: bool = False) -> None:
        """Delete automation.

        Requires the 'config' integration to be enabled in Home Assistant.

        Args:
            automation_id: Automation ID (entity ID or numeric ID)
            dry_run: If True, validate but don't delete

        Raises:
            ValidationError: If REST API unavailable
            AutomationNotFoundError: If automation not found
        """
        # Check REST API availability
        if not await self._check_rest_api():
            raise ValidationError(
                "REST API not available. Deleting automations requires the 'config' "
                "integration to be enabled in Home Assistant's configuration.yaml."
            )

        # Resolve to numeric ID if needed
        if not automation_id.isdigit():
            numeric_id = await self.client.get_automation_numeric_id(automation_id)
            if not numeric_id:
                raise AutomationNotFoundError(automation_id)
            logger.debug(f"Resolved {automation_id} to numeric ID {numeric_id}")
        else:
            numeric_id = automation_id

        if dry_run:
            logger.info(f"Dry run: would delete automation {automation_id}")
            return

        # Delete the automation
        await self.client.delete_automation_rest(numeric_id)
        logger.info(f"Deleted automation {automation_id} (numeric ID: {numeric_id})")


class AutomationWS:
    """Service for WebSocket operations on automations."""
    
    def __init__(self, client: HAClient) -> None:
        """Initialize service with HAClient."""
        self.client = client
    
    async def enable_automation(self, automation_id: str) -> None:
        """Enable automation via WebSocket."""
        await self.client.enable_automation(automation_id)
    
    async def disable_automation(self, automation_id: str) -> None:
        """Disable automation via WebSocket."""
        await self.client.disable_automation(automation_id)
    
    async def reload_automations(self) -> None:
        """Reload all automations via WebSocket."""
        await self.client.reload_automations()