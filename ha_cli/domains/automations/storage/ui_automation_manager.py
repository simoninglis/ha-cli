"""Manager for UI-style automations stored in .storage/automations."""

import logging
from typing import Any

from ....common.client import HAClient
from ....common.exceptions import NotFoundError, ValidationError
from ..models import Automation
from .automation_type_detector import AutomationTypeDetector
from .format_converter import FormatConverter

logger = logging.getLogger(__name__)


class UIAutomationManager:
    """Manage UI-style automations via REST API."""
    
    def __init__(self, client: HAClient):
        """Initialize UI automation manager.
        
        Args:
            client: Home Assistant client instance
        """
        self.client = client
    
    async def create(self, automation: Automation) -> str:
        """Create a new UI-style automation.
        
        Args:
            automation: Automation to create (will be converted to plural format)
            
        Returns:
            The created automation ID
            
        Raises:
            ValidationError: If automation data is invalid
        """
        # Generate UI-style ID if not provided
        if not automation.id:
            automation.id = AutomationTypeDetector.generate_ui_id()
        elif not AutomationTypeDetector.is_ui_id(automation.id):
            raise ValidationError(
                f"UI automations require 32-character hex IDs, got: {automation.id}"
            )
        
        # Convert to dict and then to plural format for UI
        automation_data = automation.model_dump(exclude_none=True)
        ui_data = FormatConverter.to_plural_format(automation_data)
        
        # Remove fields that shouldn't be sent
        ui_data.pop("last_triggered", None)
        ui_data.pop("trace", None)
        
        logger.debug(f"Creating UI automation with ID: {automation.id}")
        
        # POST to /api/config/automation/config/{id}
        endpoint = f"/api/config/automation/config/{automation.id}"
        try:
            await self.client._request(
                method="POST",
                endpoint=endpoint,
                json_data=ui_data,
            )
            logger.info(f"Created UI automation: {automation.id}")
            return automation.id
        except Exception as e:
            logger.error(f"Failed to create UI automation: {e}")
            raise
    
    async def update(self, automation: Automation) -> None:
        """Update an existing UI-style automation.
        
        Args:
            automation: Automation to update (must have ID)
            
        Raises:
            ValidationError: If automation ID is invalid
            NotFoundError: If automation not found
        """
        if not automation.id:
            raise ValidationError("Automation ID is required for update")
        
        if not AutomationTypeDetector.is_ui_id(automation.id):
            raise ValidationError(
                f"Not a UI-style automation ID: {automation.id}"
            )
        
        # Convert to dict and then to plural format for UI
        automation_data = automation.model_dump(exclude_none=True)
        ui_data = FormatConverter.to_plural_format(automation_data)
        
        # Remove fields that shouldn't be sent
        ui_data.pop("last_triggered", None)
        ui_data.pop("trace", None)
        
        logger.debug(f"Updating UI automation: {automation.id}")
        
        # POST to /api/config/automation/config/{id} (same as create)
        endpoint = f"/api/config/automation/config/{automation.id}"
        try:
            await self.client._request(
                method="POST",
                endpoint=endpoint,
                json_data=ui_data,
            )
            logger.info(f"Updated UI automation: {automation.id}")
        except NotFoundError:
            logger.error(f"UI automation not found: {automation.id}")
            raise
        except Exception as e:
            logger.error(f"Failed to update UI automation: {e}")
            raise
    
    async def delete(self, automation_id: str) -> None:
        """Delete a UI-style automation.
        
        Args:
            automation_id: ID of automation to delete
            
        Raises:
            ValidationError: If automation ID is invalid
            NotFoundError: If automation not found
        """
        if not AutomationTypeDetector.is_ui_id(automation_id):
            raise ValidationError(
                f"Not a UI-style automation ID: {automation_id}"
            )
        
        logger.debug(f"Deleting UI automation: {automation_id}")
        
        # DELETE to /api/config/automation/config/{id}
        endpoint = f"/api/config/automation/config/{automation_id}"
        try:
            await self.client._request(
                method="DELETE",
                endpoint=endpoint,
            )
            logger.info(f"Deleted UI automation: {automation_id}")
        except NotFoundError:
            logger.error(f"UI automation not found: {automation_id}")
            raise
        except Exception as e:
            logger.error(f"Failed to delete UI automation: {e}")
            raise
    
    async def get_config(self, automation_id: str) -> dict[str, Any]:
        """Get configuration for a specific UI automation.
        
        Note: This uses WebSocket as there's no REST endpoint for reading single automations.
        
        Args:
            automation_id: ID of automation to get
            
        Returns:
            Automation configuration in plural format
            
        Raises:
            NotFoundError: If automation not found
        """
        if not AutomationTypeDetector.is_ui_id(automation_id):
            raise ValidationError(
                f"Not a UI-style automation ID: {automation_id}"
            )
        
        # Use WebSocket to get config
        try:
            config = await self.client.get_automation_config(automation_id)
            # WebSocket returns singular format, convert to plural for consistency
            return FormatConverter.to_plural_format(config)
        except Exception as e:
            logger.error(f"Failed to get UI automation config: {e}")
            raise
    
    async def exists(self, automation_id: str) -> bool:
        """Check if a UI automation exists.
        
        Args:
            automation_id: ID to check
            
        Returns:
            True if automation exists
        """
        try:
            await self.get_config(automation_id)
            return True
        except NotFoundError:
            return False