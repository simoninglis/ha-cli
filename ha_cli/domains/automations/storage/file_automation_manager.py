"""Manager for file-based automations stored in automations.yaml."""

import asyncio
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import ruamel.yaml
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from ....common.client import HAClient
from ....common.exceptions import NotFoundError, ValidationError
from ..models import Automation
from .automation_type_detector import AutomationTypeDetector
from .format_converter import FormatConverter

logger = logging.getLogger(__name__)


class FileAutomationManager:
    """Manage file-based automations in automations.yaml."""
    
    def __init__(self, client: HAClient, automations_file: Path | None = None):
        """Initialize file automation manager.
        
        Args:
            client: Home Assistant client instance
            automations_file: Path to automations.yaml (defaults to ~/automations.yaml)
        """
        self.client = client
        self.automations_file = automations_file or Path.home() / "automations.yaml"
        self._yaml = ruamel.yaml.YAML()
        self._yaml.preserve_quotes = True
        self._yaml.default_flow_style = False
        self._yaml.width = 1000
    
    async def load_all(self) -> list[Automation]:
        """Load all automations from the file.
        
        Returns:
            List of Automation objects
            
        Raises:
            FileNotFoundError: If automations.yaml doesn't exist
        """
        if not self.automations_file.exists():
            logger.warning(f"Automations file not found: {self.automations_file}")
            return []
        
        try:
            with open(self.automations_file, 'r', encoding='utf-8') as f:
                data = self._yaml.load(f)
            
            if not data:
                return []
            
            # Ensure data is a list
            if not isinstance(data, list):
                raise ValidationError(f"Invalid automations.yaml format: expected list, got {type(data)}")
            
            automations = []
            for item in data:
                try:
                    # Ensure singular format
                    normalized = FormatConverter.normalize_format(item, "singular")
                    automation = Automation(**normalized)
                    automations.append(automation)
                except Exception as e:
                    logger.warning(f"Failed to parse automation: {e}")
                    continue
            
            return automations
            
        except Exception as e:
            logger.error(f"Failed to load automations from {self.automations_file}: {e}")
            raise
    
    async def save_all(self, automations: list[Automation]) -> None:
        """Save all automations to the file.
        
        Args:
            automations: List of automations to save
        """
        # Create backup first
        await self._create_backup()
        
        try:
            # Convert to YAML-compatible format
            yaml_data = CommentedSeq()
            
            for automation in automations:
                # Get dict representation
                data = automation.model_dump(exclude_none=True)
                
                # Ensure singular format for file storage
                data = FormatConverter.normalize_format(data, "singular")
                
                # Remove fields that shouldn't be in YAML
                data.pop("last_triggered", None)
                data.pop("trace", None)
                
                # Create CommentedMap to preserve formatting
                yaml_item = CommentedMap(data)
                yaml_data.append(yaml_item)
            
            # Write to file
            with open(self.automations_file, 'w', encoding='utf-8') as f:
                self._yaml.dump(yaml_data, f)
            
            logger.info(f"Saved {len(automations)} automations to {self.automations_file}")
            
            # Trigger Home Assistant reload
            await self._trigger_reload()
            
        except Exception as e:
            logger.error(f"Failed to save automations: {e}")
            # Try to restore backup
            await self._restore_backup()
            raise
    
    async def create(self, automation: Automation) -> str:
        """Create a new file-based automation.
        
        Args:
            automation: Automation to create
            
        Returns:
            The automation ID (may be generated if not provided)
        """
        # Validate ID format
        if automation.id and AutomationTypeDetector.is_ui_id(automation.id):
            raise ValidationError(
                f"File-based automations should not use UI-style IDs: {automation.id}"
            )
        
        # Generate ID if not provided
        if not automation.id:
            automation.id = self._generate_file_id(automation.alias)
        
        # Load existing automations
        automations = await self.load_all()
        
        # Check for duplicate ID
        if any(a.id == automation.id for a in automations):
            raise ValidationError(f"Automation with ID '{automation.id}' already exists")
        
        # Add new automation
        automations.append(automation)
        
        # Save all automations
        await self.save_all(automations)
        
        logger.info(f"Created file-based automation: {automation.id}")
        return automation.id
    
    async def update(self, automation: Automation) -> None:
        """Update an existing file-based automation.
        
        Args:
            automation: Automation to update (must have ID)
            
        Raises:
            NotFoundError: If automation not found
        """
        if not automation.id:
            raise ValidationError("Automation ID is required for update")
        
        # Load existing automations
        automations = await self.load_all()
        
        # Find and update
        found = False
        for i, existing in enumerate(automations):
            if existing.id == automation.id:
                automations[i] = automation
                found = True
                break
        
        if not found:
            raise NotFoundError(f"Automation not found: {automation.id}")
        
        # Save all automations
        await self.save_all(automations)
        
        logger.info(f"Updated file-based automation: {automation.id}")
    
    async def delete(self, automation_id: str) -> None:
        """Delete a file-based automation.
        
        Args:
            automation_id: ID of automation to delete
            
        Raises:
            NotFoundError: If automation not found
        """
        # Load existing automations
        automations = await self.load_all()
        
        # Filter out the automation to delete
        original_count = len(automations)
        automations = [a for a in automations if a.id != automation_id]
        
        if len(automations) == original_count:
            raise NotFoundError(f"Automation not found: {automation_id}")
        
        # Save remaining automations
        await self.save_all(automations)
        
        logger.info(f"Deleted file-based automation: {automation_id}")
    
    async def get_by_id(self, automation_id: str) -> Automation | None:
        """Get a specific automation by ID.
        
        Args:
            automation_id: ID to search for
            
        Returns:
            Automation if found, None otherwise
        """
        automations = await self.load_all()
        for automation in automations:
            if automation.id == automation_id:
                return automation
        return None
    
    async def exists(self, automation_id: str) -> bool:
        """Check if an automation exists.
        
        Args:
            automation_id: ID to check
            
        Returns:
            True if automation exists
        """
        automation = await self.get_by_id(automation_id)
        return automation is not None
    
    async def _create_backup(self) -> None:
        """Create a backup of the automations file."""
        if not self.automations_file.exists():
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = self.automations_file.with_suffix(f".{timestamp}.backup")
        
        try:
            shutil.copy2(self.automations_file, backup_file)
            logger.debug(f"Created backup: {backup_file}")
            
            # Keep only last 5 backups
            await self._cleanup_old_backups()
            
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
    
    async def _restore_backup(self) -> None:
        """Restore the most recent backup."""
        backup_pattern = f"{self.automations_file.stem}.*.backup"
        backups = sorted(self.automations_file.parent.glob(backup_pattern))
        
        if not backups:
            logger.warning("No backup found to restore")
            return
        
        latest_backup = backups[-1]
        try:
            shutil.copy2(latest_backup, self.automations_file)
            logger.info(f"Restored from backup: {latest_backup}")
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
    
    async def _cleanup_old_backups(self, keep_count: int = 5) -> None:
        """Clean up old backup files."""
        backup_pattern = f"{self.automations_file.stem}.*.backup"
        backups = sorted(self.automations_file.parent.glob(backup_pattern))
        
        if len(backups) > keep_count:
            for backup in backups[:-keep_count]:
                try:
                    backup.unlink()
                    logger.debug(f"Removed old backup: {backup}")
                except Exception as e:
                    logger.warning(f"Failed to remove backup {backup}: {e}")
    
    async def _trigger_reload(self) -> None:
        """Trigger Home Assistant to reload automations."""
        try:
            logger.debug("Triggering Home Assistant automation reload")
            await self.client.call_automation_service("reload", [])
            # Give HA time to reload
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning(f"Failed to trigger automation reload: {e}")
    
    def _generate_file_id(self, alias: str) -> str:
        """Generate a file-friendly automation ID from alias.
        
        Args:
            alias: Automation alias/name
            
        Returns:
            Generated ID
        """
        # Convert alias to snake_case ID
        import re
        
        # Remove special characters and convert to lowercase
        id_base = re.sub(r'[^\w\s-]', '', alias.lower())
        # Replace spaces and hyphens with underscores
        id_base = re.sub(r'[-\s]+', '_', id_base)
        # Remove leading/trailing underscores
        id_base = id_base.strip('_')
        
        # Add timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        
        return f"{id_base}_{timestamp}"