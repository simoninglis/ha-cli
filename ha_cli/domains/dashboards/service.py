"""Service layer for Home Assistant dashboard management."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import ruamel.yaml

from ...common.client import HAClient
from ...common.exceptions import (
    NotFoundError,
    ValidationError,
)
from .models import DashboardConfig, DashboardInfo


logger = logging.getLogger(__name__)


class DashboardService:
    """Service for managing Home Assistant dashboards."""
    
    def __init__(self, client: HAClient) -> None:
        """Initialize service with HAClient."""
        self.client = client
    
    async def list_dashboards(self, include_default: bool = True) -> list[DashboardInfo]:
        """List all dashboards.
        
        Args:
            include_default: Include the default dashboard in the list
            
        Returns:
            List of dashboard information
        """
        dashboards = await self.client.list_dashboards()
        
        result = []
        
        # Add default dashboard if requested
        if include_default:
            result.append(DashboardInfo(
                id="default",
                url_path="",
                title="Default",
                mode="storage",
                require_admin=False,
                show_in_sidebar=True,
            ))
        
        # Add other dashboards
        for dashboard in dashboards:
            result.append(DashboardInfo(**dashboard))
        
        return result
    
    async def get_dashboard(self, url_path: str | None = None) -> DashboardConfig:
        """Get dashboard configuration.
        
        Args:
            url_path: Dashboard URL path (None for default)
            
        Returns:
            Dashboard configuration
            
        Raises:
            NotFoundError: If dashboard not found
        """
        config_data = await self.client.get_dashboard_config(url_path)
        return DashboardConfig.from_dict(config_data)
    
    async def save_dashboard(
        self, 
        config: DashboardConfig, 
        url_path: str | None = None
    ) -> None:
        """Save dashboard configuration.
        
        Args:
            config: Dashboard configuration
            url_path: Dashboard URL path (None for default)
            
        Raises:
            ValidationError: If configuration is invalid
            NotFoundError: If dashboard not found
        """
        config_data = config.model_dump(exclude_none=True)
        await self.client.save_dashboard_config(config_data, url_path)
    
    async def create_dashboard(
        self,
        dashboard_id: str,
        url_path: str,
        title: str,
        icon: str | None = None,
        show_in_sidebar: bool = True,
        require_admin: bool = False,
    ) -> None:
        """Create a new dashboard.
        
        Args:
            dashboard_id: Unique dashboard ID
            url_path: URL path for the dashboard
            title: Dashboard title
            icon: Optional icon
            show_in_sidebar: Whether to show in sidebar
            require_admin: Whether admin access is required
            
        Raises:
            ValidationError: If dashboard already exists or invalid parameters
        """
        await self.client.create_dashboard(
            dashboard_id=dashboard_id,
            url_path=url_path,
            title=title,
            icon=icon,
            show_in_sidebar=show_in_sidebar,
            require_admin=require_admin,
        )
    
    async def update_dashboard(
        self,
        dashboard_id: str,
        url_path: str | None = None,
        title: str | None = None,
        icon: str | None = None,
        show_in_sidebar: bool | None = None,
        require_admin: bool | None = None,
    ) -> None:
        """Update dashboard settings.
        
        Args:
            dashboard_id: Dashboard ID to update
            url_path: New URL path (optional)
            title: New title (optional)
            icon: New icon (optional)
            show_in_sidebar: New sidebar visibility (optional)
            require_admin: New admin requirement (optional)
            
        Raises:
            NotFoundError: If dashboard not found
            ValidationError: If invalid parameters
        """
        await self.client.update_dashboard(
            dashboard_id=dashboard_id,
            url_path=url_path,
            title=title,
            icon=icon,
            show_in_sidebar=show_in_sidebar,
            require_admin=require_admin,
        )
    
    async def delete_dashboard(self, dashboard_id: str) -> None:
        """Delete a dashboard.
        
        Args:
            dashboard_id: Dashboard ID to delete
            
        Raises:
            NotFoundError: If dashboard not found
            ValidationError: If trying to delete default dashboard
        """
        await self.client.delete_dashboard(dashboard_id)
    
    async def backup_dashboard(
        self, 
        url_path: str | None = None, 
        output_file: str | None = None,
        format: Literal["json", "yaml"] = "yaml",
    ) -> str:
        """Backup dashboard configuration to file.
        
        Args:
            url_path: Dashboard URL path (None for default)
            output_file: Output file path (auto-generated if None)
            format: Output format (json or yaml)
            
        Returns:
            Path to backup file
            
        Raises:
            NotFoundError: If dashboard not found
        """
        # Get dashboard config
        config = await self.get_dashboard(url_path)
        
        # Generate filename if not provided
        if not output_file:
            dashboard_name = url_path or "default"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"dashboard_{dashboard_name}_{timestamp}.{format}"
        
        # Save to file
        path = Path(output_file)
        
        if format == "json":
            with open(path, "w", encoding="utf-8") as f:
                json.dump(config.model_dump(exclude_none=True), f, indent=2)
        else:  # yaml
            yaml = ruamel.yaml.YAML()
            yaml.preserve_quotes = True
            yaml.default_flow_style = False
            yaml.width = 1000
            
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(config.model_dump(exclude_none=True), f)
        
        logger.info(f"Dashboard backed up to: {path}")
        return str(path)
    
    async def restore_dashboard(
        self,
        input_file: str,
        url_path: str | None = None,
        validate_only: bool = False,
    ) -> None:
        """Restore dashboard configuration from file.
        
        Args:
            input_file: Input file path
            url_path: Dashboard URL path (None for default)
            validate_only: Only validate without saving
            
        Raises:
            ValidationError: If configuration is invalid
            NotFoundError: If dashboard not found
        """
        path = Path(input_file)
        if not path.exists():
            raise ValidationError(f"File not found: {input_file}")
        
        # Load configuration
        if path.suffix == ".json":
            with open(path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        else:  # yaml
            yaml = ruamel.yaml.YAML(typ='safe')
            with open(path, "r", encoding="utf-8") as f:
                config_data = yaml.load(f)
        
        # Parse and validate
        config = DashboardConfig.from_dict(config_data)
        
        if not validate_only:
            await self.save_dashboard(config, url_path)
            logger.info(f"Dashboard restored from: {path}")
    
    async def get_entity_references(
        self, 
        url_path: str | None = None,
        include_views: bool = True
    ) -> list[str]:
        """Get all entity references in a dashboard.
        
        Args:
            url_path: Dashboard URL path (None for default)
            include_views: Include entities from all views in the dashboard
            
        Returns:
            List of unique entity IDs referenced in the dashboard
            
        Raises:
            NotFoundError: If dashboard not found
        """
        config = await self.get_dashboard(url_path)
        return config.get_entity_references()
    
    async def get_entity_references_with_location(
        self,
        url_path: str | None = None
    ) -> dict[str, list[str]]:
        """Get entity references with their locations (views) in a dashboard.
        
        Args:
            url_path: Dashboard URL path (None for default)
            
        Returns:
            Dictionary mapping entity IDs to list of view paths where they appear
            
        Raises:
            NotFoundError: If dashboard not found
        """
        config = await self.get_dashboard(url_path)
        dashboard_name = url_path or "default"
        entity_locations: dict[str, list[str]] = {}
        
        # Get entities from top-level cards (no view)
        if hasattr(config, 'cards') and config.cards:
            for card in config.cards:
                entities = self._extract_entities_from_card(card.model_dump() if hasattr(card, 'model_dump') else card)
                for entity in entities:
                    if entity not in entity_locations:
                        entity_locations[entity] = []
                    entity_locations[entity].append(dashboard_name)
        
        # Get entities from views
        if hasattr(config, 'views') and config.views:
            for view in config.views:
                view_dict: dict[str, Any] = view.model_dump() if hasattr(view, 'model_dump') else dict(view) if isinstance(view, dict) else {}  # type: ignore[unreachable]
                view_path = view_dict.get('path', view_dict.get('title', 'untitled'))
                view_location = f"{dashboard_name}/{view_path}"

                if 'cards' in view_dict:
                    for card in view_dict['cards']:
                        entities = self._extract_entities_from_card(card)
                        for entity in entities:
                            if entity not in entity_locations:
                                entity_locations[entity] = []
                            entity_locations[entity].append(view_location)
        
        return entity_locations
    
    def _extract_entities_from_card(self, card: dict) -> set[str]:
        """Extract entity IDs from a card configuration."""
        entities = set()
        
        def extract_from_dict(d: dict) -> None:
            """Recursively extract entity IDs from dictionary."""
            for key, value in d.items():
                if key in ['entity', 'entity_id'] and isinstance(value, str):
                    entities.add(value)
                elif key == 'entities' and isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):
                            entities.add(item)
                        elif isinstance(item, dict):
                            # Handle entity objects in entities list
                            if 'entity' in item:
                                entities.add(item['entity'])
                            extract_from_dict(item)
                elif isinstance(value, dict):
                    extract_from_dict(value)
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            extract_from_dict(item)
        
        extract_from_dict(card)
        return entities
    
    async def update_entity_references(
        self,
        url_path: str | None = None,
        entity_map: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> dict[str, list[str]]:
        """Update entity references in a dashboard.
        
        Args:
            url_path: Dashboard URL path (None for default)
            entity_map: Mapping of old entity IDs to new entity IDs
            dry_run: If True, only return what would be changed without saving
            
        Returns:
            Dictionary with 'updated' and 'not_found' entity lists
            
        Raises:
            NotFoundError: If dashboard not found
        """
        if not entity_map:
            raise ValidationError("Entity map is required")
        
        # Get current config
        config = await self.get_dashboard(url_path)
        config_dict = config.model_dump()
        
        # Track updates
        updated_entities = []
        not_found_entities = list(entity_map.keys())
        
        def update_entity_in_dict(data: dict[str, Any]) -> None:
            """Recursively update entity IDs in dictionary."""
            for key, value in data.items():
                if key in ["entity", "entity_id", "device_id", "area_id"] and isinstance(value, str):
                    if value in entity_map:
                        data[key] = entity_map[value]
                        if value in not_found_entities:
                            not_found_entities.remove(value)
                        if value not in updated_entities:
                            updated_entities.append(value)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, str) and item in entity_map:
                            value[i] = entity_map[item]
                            if item in not_found_entities:
                                not_found_entities.remove(item)
                            if item not in updated_entities:
                                updated_entities.append(item)
                        elif isinstance(item, dict):
                            update_entity_in_dict(item)
                elif isinstance(value, dict):
                    update_entity_in_dict(value)
        
        # Update entities in config
        update_entity_in_dict(config_dict)
        
        # Save if not dry run
        if not dry_run and updated_entities:
            updated_config = DashboardConfig.from_dict(config_dict)
            await self.save_dashboard(updated_config, url_path)
            logger.info(f"Updated {len(updated_entities)} entity references in dashboard")
        
        return {
            "updated": updated_entities,
            "not_found": not_found_entities,
        }