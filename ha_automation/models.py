"""Data models for Home Assistant automations using Pydantic v2."""

from datetime import datetime
from typing import Any, Literal

import ruamel.yaml
from pydantic import BaseModel, Field, model_validator


class Automation(BaseModel):
    """Home Assistant automation model according to spec."""
    
    id: str | None = None
    alias: str
    trigger: list[Any]
    condition: list[Any] | None = None
    action: list[Any]
    mode: Literal["single", "restart", "queued", "parallel"] = "single"
    max: int | None = None
    max_exceeded: Literal["silent", "critical", "fatal", "error", "warning", "warn", "info", "debug", "notset"] | None = None
    trace: dict[str, Any] | None = None
    last_triggered: datetime | None = None
    variables: dict[str, Any] | None = None
    
    model_config = {
        "validate_assignment": True,
        "extra": "allow",
    }
    
    @model_validator(mode="before")
    @classmethod
    def validate_fields(cls, values: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize fields."""
        # Handle both singular and plural forms
        # triggers -> trigger
        if "triggers" in values:
            values["trigger"] = values.pop("triggers")
        # conditions -> condition  
        if "conditions" in values:
            values["condition"] = values.pop("conditions")
        # actions -> action (less common but for completeness)
        if "actions" in values:
            values["action"] = values.pop("actions")
            
        # Ensure trigger and action are lists
        if "trigger" in values and not isinstance(values["trigger"], list):
            values["trigger"] = [values["trigger"]]
        if "action" in values and not isinstance(values["action"], list):
            values["action"] = [values["action"]]
        if "condition" in values and values["condition"] is not None and not isinstance(values["condition"], list):
            values["condition"] = [values["condition"]]
        return values
    
    def to_yaml(self) -> str:
        """Convert to YAML string using ruamel.yaml."""
        yaml = ruamel.yaml.YAML()
        yaml.preserve_quotes = True
        yaml.default_flow_style = False
        yaml.width = 1000
        
        # Convert to dict and remove None values
        # Exclude fields that shouldn't be in YAML
        exclude_fields = {"id", "last_triggered", "trace"}
        data = self.model_dump(exclude_none=True)
        
        # Remove excluded fields if present
        for field in exclude_fields:
            data.pop(field, None)
        
        import io
        stream = io.StringIO()
        yaml.dump(data, stream)
        return stream.getvalue()
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Automation":
        """Create Automation from YAML string."""
        yaml = ruamel.yaml.YAML()
        data = yaml.load(yaml_str)
        return cls(**data)
    
    @classmethod
    def from_yaml_file(cls, file_path: str) -> "Automation":
        """Create Automation from YAML file."""
        with open(file_path, encoding="utf-8") as f:
            return cls.from_yaml(f.read())
    
    def to_json_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return self.model_dump(exclude_none=True, mode="json")


class AutomationListResponse(BaseModel):
    """Response model for automation list."""
    
    result: list[dict[str, Any]]
    
    def to_automations(self) -> list[Automation]:
        """Convert response to list of Automation objects."""
        automations = []
        for item in self.result:
            # Extract automation data from response
            # Only include fields that are present to allow validation to catch missing required fields
            automation_data = {"id": item.get("id")}
            
            if "alias" in item:
                automation_data["alias"] = item["alias"]
            elif "id" in item:
                automation_data["alias"] = item["id"]  # Fallback to ID
                
            if "trigger" in item:
                automation_data["trigger"] = item["trigger"]
            if "action" in item:
                automation_data["action"] = item["action"]
            if "condition" in item:
                automation_data["condition"] = item["condition"]
            if "mode" in item:
                automation_data["mode"] = item["mode"]
            if "max" in item:
                automation_data["max"] = item["max"]
            if "max_exceeded" in item:
                automation_data["max_exceeded"] = item["max_exceeded"]
            if "variables" in item:
                automation_data["variables"] = item["variables"]
            
            # Add last_triggered if available
            if "last_triggered" in item and item["last_triggered"]:
                try:
                    automation_data["last_triggered"] = datetime.fromisoformat(item["last_triggered"])
                except (ValueError, TypeError):
                    pass
            
            try:
                automations.append(Automation(**automation_data))
            except Exception as e:
                # Log error but continue processing other automations
                import logging
                logging.warning(f"Error parsing automation {item.get('id', 'unknown')}: {e}")
                continue
        
        return automations


class AutomationState(BaseModel):
    """Home Assistant automation state from WebSocket."""
    
    entity_id: str
    state: Literal["on", "off", "unavailable", "unknown"]
    attributes: dict[str, Any] = Field(default_factory=dict)
    last_changed: datetime | None = None
    last_updated: datetime | None = None
    
    @property
    def automation_id(self) -> str:
        """Extract automation ID from entity_id."""
        return self.entity_id.replace("automation.", "")
    
    @property
    def is_enabled(self) -> bool:
        """Check if automation is enabled."""
        return self.state == "on"
    
    @property
    def friendly_name(self) -> str:
        """Get friendly name from attributes."""
        return self.attributes.get("friendly_name", self.automation_id)