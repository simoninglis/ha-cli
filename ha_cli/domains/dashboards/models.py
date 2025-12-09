"""Data models for Home Assistant dashboards using Pydantic v2."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class DashboardInfo(BaseModel):
    """Dashboard list item from lovelace/dashboards/list."""
    
    id: str
    url_path: str
    require_admin: bool
    show_in_sidebar: bool
    icon: str | None = None
    title: str | None = None
    mode: Literal["storage", "yaml"] = "storage"


class CardConfig(BaseModel):
    """Generic card configuration."""
    
    type: str
    title: str | None = None
    entity: str | None = None
    entities: list[str | dict[str, Any]] | None = None
    
    # Common action fields that may contain entities
    tap_action: dict[str, Any] | None = None
    hold_action: dict[str, Any] | None = None
    double_tap_action: dict[str, Any] | None = None
    
    # Allow extra fields for various card types
    model_config = {
        "extra": "allow",
    }
    
    def get_entity_references(self) -> list[str]:
        """Extract all entity references from the card."""
        entities = []
        
        # Direct entity reference
        if self.entity:
            entities.append(self.entity)
        
        # Entity list (can be strings or entity objects)
        if self.entities:
            for item in self.entities:
                if isinstance(item, str):
                    entities.append(item)
                elif isinstance(item, dict) and 'entity' in item:
                    entities.append(item['entity'])
        
        # Extract from actions
        for action_field in ["tap_action", "hold_action", "double_tap_action"]:
            action = getattr(self, action_field)
            if action and isinstance(action, dict):
                # navigation target entity
                if action.get("navigation_path"):
                    path = action["navigation_path"]
                    if isinstance(path, str) and path.startswith("/lovelace/"):
                        # Could contain entity in URL
                        pass
                
                # service call entities
                if action.get("service"):
                    target = action.get("target", {})
                    if isinstance(target, dict) and target.get("entity_id"):
                        entity_id = target["entity_id"]
                        if isinstance(entity_id, str):
                            entities.append(entity_id)
                        elif isinstance(entity_id, list):
                            entities.extend(entity_id)
        
        # Extract from extra fields (card-specific)
        extra_fields = self.model_dump(exclude={"type", "title", "entity", "entities", 
                                                "tap_action", "hold_action", "double_tap_action"})
        entities.extend(self._extract_entities_from_dict(extra_fields))
        
        # Remove duplicates while preserving order
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity not in seen and self._is_valid_entity_id(entity):
                seen.add(entity)
                unique_entities.append(entity)
        
        return unique_entities
    
    def _extract_entities_from_dict(self, data: dict[str, Any], depth: int = 0) -> list[str]:
        """Recursively extract entity IDs from nested structures."""
        if depth > 10:  # Prevent infinite recursion
            return []
        
        entities = []
        
        for key, value in data.items():
            # Common entity field names
            if key in ["entity", "entity_id", "device_id", "area_id"]:
                if isinstance(value, str) and self._is_valid_entity_id(value):
                    entities.append(value)
                elif isinstance(value, list):
                    entities.extend([v for v in value if isinstance(v, str) and self._is_valid_entity_id(v)])
            
            # Recursively check nested structures
            elif isinstance(value, dict):
                entities.extend(self._extract_entities_from_dict(value, depth + 1))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        entities.extend(self._extract_entities_from_dict(item, depth + 1))
                    elif isinstance(item, str) and key == "entities" and self._is_valid_entity_id(item):
                        entities.append(item)
        
        return entities
    
    def _is_valid_entity_id(self, entity_id: Any) -> bool:
        """Check if string is a valid entity ID format."""
        if not isinstance(entity_id, str):
            return False
        
        # Entity IDs have domain.object_id format
        parts = entity_id.split(".", 1)
        if len(parts) != 2:
            return False
        
        domain, object_id = parts
        
        # Common domains
        valid_domains = {
            "alarm_control_panel", "automation", "binary_sensor", "button", "camera", 
            "climate", "cover", "device_tracker", "fan", "group", "input_boolean",
            "input_datetime", "input_number", "input_select", "input_text",
            "light", "lock", "media_player", "person", "scene", "script",
            "sensor", "sun", "switch", "timer", "vacuum", "water_heater", 
            "weather", "zone"
        }
        
        return domain in valid_domains and len(object_id) > 0


class ViewConfig(BaseModel):
    """Dashboard view/tab configuration."""
    
    title: str | None = None
    path: str | None = None
    icon: str | None = None
    badges: list[str | dict[str, Any]] | None = None
    cards: list[CardConfig] = Field(default_factory=list)
    theme: str | None = None
    background: str | None = None
    visible: list[dict[str, Any]] | bool | None = None
    
    model_config = {
        "extra": "allow",
    }
    
    def get_entity_references(self) -> list[str]:
        """Extract all entity references from the view."""
        entities = []
        
        # Extract from cards
        for card in self.cards:
            entities.extend(card.get_entity_references())
        
        # Extract from badges (legacy format)
        if self.badges:
            for badge in self.badges:
                if isinstance(badge, str) and "." in badge:
                    entities.append(badge)
                elif isinstance(badge, dict) and badge.get("entity"):
                    entities.append(badge["entity"])
        
        # Remove duplicates while preserving order
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity not in seen:
                seen.add(entity)
                unique_entities.append(entity)
        
        return unique_entities


class DashboardConfig(BaseModel):
    """Complete dashboard configuration."""
    
    title: str | None = None
    views: list[ViewConfig] = Field(default_factory=list)
    
    # Storage mode fields
    version: int | None = None
    
    model_config = {
        "extra": "allow",
    }
    
    def get_entity_references(self) -> list[str]:
        """Extract all entity references from the dashboard."""
        entities = []
        
        for view in self.views:
            entities.extend(view.get_entity_references())
        
        # Remove duplicates while preserving order
        seen = set()
        unique_entities = []
        for entity in entities:
            if entity not in seen:
                seen.add(entity)
                unique_entities.append(entity)
        
        return unique_entities
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DashboardConfig":
        """Create dashboard config from raw dictionary."""
        # Handle views
        views = []
        if "views" in data:
            for view_data in data["views"]:
                # Handle cards in view
                cards = []
                if "cards" in view_data:
                    for card_data in view_data["cards"]:
                        cards.append(CardConfig(**card_data))
                
                view_data["cards"] = cards
                views.append(ViewConfig(**view_data))
        
        data["views"] = views
        return cls(**data)