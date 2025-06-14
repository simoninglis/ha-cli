"""Service layer for Home Assistant automation management."""

import logging
from pathlib import Path
from typing import Any

from .client import HAClient
from .exceptions import (
    AutomationNotFoundError,
    ValidationError,
)
from .models import Automation, AutomationListResponse

logger = logging.getLogger(__name__)


class AutomationCRUD:
    """Service for CRUD operations on automations."""
    
    def __init__(self, client: HAClient) -> None:
        """Initialize service with HAClient."""
        self.client = client
    
    async def list_automations(self, json_output: bool = False) -> list[Automation] | list[dict[str, Any]]:
        """List all automations.
        
        Args:
            json_output: Return raw JSON instead of Automation objects
            
        Returns:
            List of automations
        """
        raw_data = await self.client.list_automations()
        
        if json_output:
            return raw_data
        
        # Parse response
        response = AutomationListResponse(result=raw_data)
        return response.to_automations()
    
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
            if "404" in str(e):
                raise AutomationNotFoundError(automation_id)
            raise
    
    async def create_automation(self, file_path: str) -> str:
        """Create automation from file.
        
        Args:
            file_path: Path to YAML/JSON file
            
        Returns:
            New automation ID
        """
        path = Path(file_path)
        if not path.exists():
            raise ValidationError(f"File not found: {file_path}")
        
        # Load automation from file
        if path.suffix in [".yaml", ".yml"]:
            automation = Automation.from_yaml_file(str(path))
        elif path.suffix == ".json":
            import json
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            automation = Automation(**data)
        else:
            raise ValidationError("File must be YAML or JSON")
        
        # Validate
        self._validate_automation(automation)
        
        # Create via API
        result = await self.client.create_automation(automation.to_json_dict())
        
        # Extract ID from result
        return result.get("id", "unknown")
    
    async def update_automation(self, automation_id: str, file_path: str) -> None:
        """Update automation from file.
        
        Args:
            automation_id: Automation ID
            file_path: Path to YAML/JSON file
        """
        path = Path(file_path)
        if not path.exists():
            raise ValidationError(f"File not found: {file_path}")
        
        # Load automation from file
        if path.suffix in [".yaml", ".yml"]:
            automation = Automation.from_yaml_file(str(path))
        elif path.suffix == ".json":
            import json
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            automation = Automation(**data)
        else:
            raise ValidationError("File must be YAML or JSON")
        
        # Validate
        self._validate_automation(automation)
        
        # Update via API
        await self.client.update_automation(automation_id, automation.to_json_dict())
    
    async def delete_automation(self, automation_id: str) -> None:
        """Delete automation.
        
        Args:
            automation_id: Automation ID
        """
        await self.client.delete_automation(automation_id)
    
    def _validate_automation(self, automation: Automation) -> None:
        """Validate automation before create/update.
        
        Args:
            automation: Automation to validate
            
        Raises:
            ValidationError: If invalid
        """
        if not automation.alias:
            raise ValidationError("Automation must have an alias")
        
        if not automation.trigger:
            raise ValidationError("Automation must have at least one trigger")
        
        if not automation.action:
            raise ValidationError("Automation must have at least one action")
        
        # Validate max for queued/parallel modes
        if automation.mode in ["queued", "parallel"] and automation.max is None:
            raise ValidationError(f"Mode '{automation.mode}' requires 'max' to be set")


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