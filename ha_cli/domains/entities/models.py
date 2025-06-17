"""Data models for entity management."""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator


class Entity(BaseModel):
    """Represents a Home Assistant entity."""
    
    entity_id: str = Field(..., description="The entity ID (e.g., 'light.living_room')")
    friendly_name: str = Field("", description="Human-readable name")
    domain: str = Field(..., description="Entity domain (e.g., 'light', 'sensor')")
    state: str = Field("", description="Current state of the entity")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="Entity attributes")
    last_changed: Optional[datetime] = Field(None, description="When the entity last changed")
    last_updated: Optional[datetime] = Field(None, description="When the entity was last updated")
    
    # Note: We discovered that Home Assistant can send entity IDs with embedded newlines
    # However, the main issue was with print() modifying output, not the data itself
    # Keeping minimal sanitization for actual problematic cases
    
    @validator('entity_id', pre=True)
    def validate_entity_id(cls, v):
        """Ensure entity_id is valid."""
        if isinstance(v, str):
            # Only remove NULL characters which are never valid
            # Keep newlines/tabs in case they're somehow legitimate
            import re
            return re.sub(r'[\x00]', '', v)
        return v
    
    @classmethod
    def from_ha_state(cls, state_data: Dict[str, Any]) -> "Entity":
        """Create Entity from Home Assistant state data."""
        entity_id = state_data["entity_id"]
        domain = entity_id.split(".", 1)[0]
        
        # Parse timestamps
        last_changed = None
        last_updated = None
        if state_data.get("last_changed"):
            try:
                last_changed = datetime.fromisoformat(state_data["last_changed"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        if state_data.get("last_updated"):
            try:
                last_updated = datetime.fromisoformat(state_data["last_updated"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        
        return cls(
            entity_id=entity_id,
            friendly_name=state_data.get("attributes", {}).get("friendly_name", ""),
            domain=domain,
            state=state_data.get("state", ""),
            attributes=state_data.get("attributes", {}),
            last_changed=last_changed,
            last_updated=last_updated,
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_id": self.entity_id,
            "friendly_name": self.friendly_name,
            "domain": self.domain,
            "state": self.state,
            "attributes": self.attributes,
            "last_changed": self.last_changed.isoformat() if self.last_changed else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


class RenameOperation(BaseModel):
    """Represents a single entity rename operation."""
    
    old_entity_id: str = Field(..., description="Current entity ID")
    new_entity_id: str = Field(..., description="New entity ID")
    friendly_name: str = Field("", description="Entity friendly name for reference")
    
    def validate_ids(self) -> List[str]:
        """Validate the rename operation and return any issues."""
        issues = []
        
        if self.old_entity_id == self.new_entity_id:
            issues.append("Old and new entity IDs are identical")
        
        if not self.old_entity_id or "." not in self.old_entity_id:
            issues.append("Invalid old entity ID format")
        
        if not self.new_entity_id or "." not in self.new_entity_id:
            issues.append("Invalid new entity ID format")
        
        # Check if domains match
        old_domain = self.old_entity_id.split(".", 1)[0]
        new_domain = self.new_entity_id.split(".", 1)[0]
        if old_domain != new_domain:
            issues.append(f"Domain change not allowed: {old_domain} -> {new_domain}")
        
        return issues


class RenamePreview(BaseModel):
    """Preview of rename operations before execution."""
    
    operations: List[RenameOperation] = Field(default_factory=list, description="List of rename operations")
    total_count: int = Field(0, description="Total number of operations")
    valid_count: int = Field(0, description="Number of valid operations")
    invalid_operations: List[Dict[str, Any]] = Field(default_factory=list, description="Invalid operations with reasons")
    warnings: List[str] = Field(default_factory=list, description="General warnings")
    
    @classmethod
    def from_operations(cls, operations: List[RenameOperation]) -> "RenamePreview":
        """Create preview from list of operations."""
        valid_ops = []
        invalid_ops = []
        warnings = []
        
        for op in operations:
            issues = op.validate_ids()
            if issues:
                invalid_ops.append({
                    "operation": op.model_dump(),
                    "issues": issues
                })
            else:
                valid_ops.append(op)
        
        # Add general warnings
        if len(valid_ops) > 50:
            warnings.append(f"Large number of operations ({len(valid_ops)}) - consider breaking into smaller batches")
        
        domains = set(op.new_entity_id.split(".", 1)[0] for op in valid_ops)
        if len(domains) > 5:
            warnings.append(f"Operations span many domains ({len(domains)}) - ensure coordination")
        
        return cls(
            operations=valid_ops,
            total_count=len(operations),
            valid_count=len(valid_ops),
            invalid_operations=invalid_ops,
            warnings=warnings,
        )


class RenameResult(BaseModel):
    """Result of a rename operation."""
    
    operation: RenameOperation = Field(..., description="The rename operation")
    success: bool = Field(..., description="Whether the operation succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the operation was performed")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "old_entity_id": self.operation.old_entity_id,
            "new_entity_id": self.operation.new_entity_id,
            "friendly_name": self.operation.friendly_name,
            "success": self.success,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }


class EntityImpactAnalysis(BaseModel):
    """Analysis of the impact of entity changes on automations and dashboards."""
    
    entity_id: str = Field(..., description="Entity being analyzed")
    automation_references: List[str] = Field(default_factory=list, description="Automation IDs that reference this entity")
    dashboard_references: List[str] = Field(default_factory=list, description="Dashboard IDs that reference this entity")
    total_references: int = Field(0, description="Total number of references found")
    impact_level: str = Field("low", description="Impact level: low, medium, high")
    recommendations: List[str] = Field(default_factory=list, description="Recommended actions")
    
    @classmethod
    def create(cls, entity_id: str, automation_refs: List[str], dashboard_refs: List[str]) -> "EntityImpactAnalysis":
        """Create impact analysis from reference lists."""
        total_refs = len(automation_refs) + len(dashboard_refs)
        
        # Determine impact level
        if total_refs == 0:
            impact_level = "low"
        elif total_refs <= 5:
            impact_level = "medium"
        else:
            impact_level = "high"
        
        # Generate recommendations
        recommendations = []
        if automation_refs:
            recommendations.append(f"Review {len(automation_refs)} automation(s) after renaming")
        if dashboard_refs:
            recommendations.append(f"Update {len(dashboard_refs)} dashboard(s) after renaming")
        if total_refs > 10:
            recommendations.append("Consider impact on system performance during rename")
        if total_refs == 0:
            recommendations.append("No references found - rename should be safe")
        
        return cls(
            entity_id=entity_id,
            automation_references=automation_refs,
            dashboard_references=dashboard_refs,
            total_references=total_refs,
            impact_level=impact_level,
            recommendations=recommendations,
        )