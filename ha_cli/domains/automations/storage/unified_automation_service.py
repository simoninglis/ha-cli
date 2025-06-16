"""Unified service for managing both UI and file-based automations."""

import logging
from pathlib import Path
from typing import Any, Literal

from ....common.client import HAClient
from ....common.exceptions import NotFoundError, ValidationError
from ..models import Automation
from .automation_type_detector import AutomationTypeDetector
from .file_automation_manager import FileAutomationManager
from .format_converter import FormatConverter
from .ui_automation_manager import UIAutomationManager

logger = logging.getLogger(__name__)


class UnifiedAutomationService:
    """Unified interface for managing both UI and file-based automations."""
    
    def __init__(self, client: HAClient, automations_file: Path | None = None):
        """Initialize unified automation service.
        
        Args:
            client: Home Assistant client instance
            automations_file: Path to automations.yaml (for file-based automations)
        """
        self.client = client
        self.ui_manager = UIAutomationManager(client)
        self.file_manager = FileAutomationManager(client, automations_file)
        self.detector = AutomationTypeDetector()
    
    async def list_all(self, use_websocket: bool = False) -> list[Automation]:
        """List all automations from both UI and file storage.
        
        Args:
            use_websocket: Force WebSocket mode (for when REST API unavailable)
        
        Returns:
            Combined list of all automations
        """
        # Get automations via REST API or WebSocket fallback
        try:
            if use_websocket:
                raise NotFoundError("Forcing WebSocket mode")
            raw_automations = await self.client.list_automations()
            ws_automations = [Automation(**a) for a in raw_automations]
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower() or use_websocket:
                # Use WebSocket fallback
                logger.warning("Using WebSocket to list automations (limited info)")
                states = await self.client.get_automation_states()
                ws_automations = []
                for state in states:
                    entity_id = state.get("entity_id", "")
                    automation_id = entity_id.replace("automation.", "")
                    attributes = state.get("attributes", {})
                    
                    # Create minimal automation object
                    automation = Automation(
                        id=automation_id,
                        alias=attributes.get("friendly_name", automation_id),
                        mode=attributes.get("mode", "single"),
                        enabled=state.get("state") == "on",
                        description="Full configuration not available via WebSocket",
                        trigger=[],
                        action=[]
                    )
                    ws_automations.append(automation)
            else:
                raise
        
        # Also load file automations directly to ensure consistency
        file_automations = await self.file_manager.load_all()
        
        # Create a map of file automation IDs for deduplication
        file_ids = {a.id for a in file_automations if a.id}
        
        # Combine and deduplicate
        all_automations = []
        seen_ids = set()
        
        # Add all WebSocket automations
        for automation in ws_automations:
            if automation.id:
                if automation.id not in seen_ids:
                    all_automations.append(automation)
                    seen_ids.add(automation.id)
            else:
                # Always include automations without IDs
                all_automations.append(automation)
        
        # Add any file automations not in WebSocket response
        for automation in file_automations:
            if automation.id:
                if automation.id not in seen_ids:
                    all_automations.append(automation)
                    seen_ids.add(automation.id)
            else:
                # Always include automations without IDs
                all_automations.append(automation)
        
        return all_automations
    
    async def get_by_id(self, automation_id: str) -> Automation:
        """Get a specific automation by ID.
        
        Args:
            automation_id: Automation ID to retrieve
            
        Returns:
            Automation object
            
        Raises:
            NotFoundError: If automation not found
        """
        # Try to get via WebSocket first (works for both types)
        try:
            config = await self.client.get_automation_config(automation_id)
            # Normalize to singular format
            config = FormatConverter.normalize_format(config, "singular")
            return Automation(**config)
        except NotFoundError:
            # If not found via WebSocket, try file manager
            automation = await self.file_manager.get_by_id(automation_id)
            if automation:
                return automation
            raise NotFoundError(f"Automation not found: {automation_id}")
    
    async def create(
        self,
        automation: Automation,
        storage_type: Literal["ui", "file", "auto"] = "auto"
    ) -> str:
        """Create a new automation in the specified storage.
        
        Args:
            automation: Automation to create
            storage_type: Target storage type ("ui", "file", or "auto")
            
        Returns:
            Created automation ID
            
        Raises:
            ValidationError: If automation data is invalid
        """
        # Determine storage type
        if storage_type == "auto":
            # Default to file-based for new automations unless ID suggests UI
            if automation.id and self.detector.is_ui_id(automation.id):
                storage_type = "ui"
            else:
                storage_type = "file"
        
        # Validate ID format for chosen storage
        if storage_type == "ui":
            if automation.id and not self.detector.is_ui_id(automation.id):
                logger.warning(
                    f"UI storage requested but ID '{automation.id}' is not UI format. "
                    "Generating new UI ID."
                )
                automation.id = self.detector.generate_ui_id()
            return await self.ui_manager.create(automation)
        else:  # file
            if automation.id and self.detector.is_ui_id(automation.id):
                logger.warning(
                    f"File storage requested but ID '{automation.id}' is UI format. "
                    "Clearing ID to generate file-friendly one."
                )
                automation.id = None
            return await self.file_manager.create(automation)
    
    async def update(self, automation: Automation) -> None:
        """Update an existing automation.
        
        Auto-detects storage type based on automation ID.
        
        Args:
            automation: Automation to update (must have ID)
            
        Raises:
            NotFoundError: If automation not found
            ValidationError: If automation data is invalid
        """
        if not automation.id:
            raise ValidationError("Automation ID is required for update")
        
        # Detect storage type
        storage_type = self.detector.detect_automation_type(automation)
        
        if storage_type == "ui":
            await self.ui_manager.update(automation)
        else:
            await self.file_manager.update(automation)
    
    async def delete(self, automation_id: str) -> None:
        """Delete an automation.
        
        Auto-detects storage type based on automation ID.
        
        Args:
            automation_id: ID of automation to delete
            
        Raises:
            NotFoundError: If automation not found
        """
        # Detect storage type by ID pattern
        if self.detector.is_ui_id(automation_id):
            await self.ui_manager.delete(automation_id)
        else:
            # Try file storage first
            try:
                await self.file_manager.delete(automation_id)
            except NotFoundError:
                # If not in file storage, it might be a UI automation with custom ID
                # Try UI manager as fallback
                await self.ui_manager.delete(automation_id)
    
    async def migrate(
        self,
        automation_id: str,
        target_storage: Literal["ui", "file"]
    ) -> str:
        """Migrate an automation between storage types.
        
        Args:
            automation_id: ID of automation to migrate
            target_storage: Target storage type
            
        Returns:
            New automation ID (may change during migration)
            
        Raises:
            NotFoundError: If automation not found
            ValidationError: If migration not possible
        """
        # Get the automation
        automation = await self.get_by_id(automation_id)
        
        # Detect current storage type
        current_storage = self.detector.detect_automation_type(automation)
        
        if current_storage == target_storage:
            logger.info(f"Automation {automation_id} is already in {target_storage} storage")
            return automation_id
        
        # Delete from current storage
        await self.delete(automation_id)
        
        # Create in target storage
        if target_storage == "ui":
            # Clear ID to generate new UI-style ID
            automation.id = None
        else:  # file
            # Clear ID if it's UI-style
            if self.detector.is_ui_id(automation.id):
                automation.id = None
        
        new_id = await self.create(automation, storage_type=target_storage)
        
        logger.info(
            f"Migrated automation from {current_storage} to {target_storage} storage. "
            f"Old ID: {automation_id}, New ID: {new_id}"
        )
        
        return new_id
    
    async def analyze_storage(self) -> dict[str, Any]:
        """Analyze the distribution of automations across storage types.
        
        Returns:
            Analysis results with counts and statistics
        """
        all_automations = await self.list_all()
        return self.detector.analyze_automation_set(all_automations)
    
    async def validate_all(self) -> dict[str, list[str]]:
        """Validate all automations and report issues.
        
        Returns:
            Dictionary mapping automation IDs to lists of validation issues
        """
        all_automations = await self.list_all()
        issues = {}
        
        for automation in all_automations:
            automation_issues = []
            
            # Check ID format matches storage type
            storage_type = self.detector.detect_automation_type(automation)
            if not self.detector.validate_id_format(automation.id, storage_type):
                automation_issues.append(
                    f"ID format mismatch: '{automation.id}' in {storage_type} storage"
                )
            
            # Check for required fields
            if not automation.trigger:
                automation_issues.append("Missing required field: trigger")
            if not automation.action:
                automation_issues.append("Missing required field: action")
            
            if automation_issues:
                issues[automation.id or automation.alias] = automation_issues
        
        return issues