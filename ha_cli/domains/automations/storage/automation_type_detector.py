"""Detect whether an automation is UI-based or file-based."""

import re
from enum import Enum
from typing import Any, Literal

from ..models import Automation


class StorageType(Enum):
    """Automation storage type."""
    
    UI = "ui"
    FILE = "file"
    AUTO = "auto"


class AutomationTypeDetector:
    """Detect and analyze automation storage types."""
    
    # UI-style automations use 32-character hex UUIDs
    UI_ID_PATTERN = re.compile(r'^[0-9a-f]{32}$')
    
    @classmethod
    def detect_automation_type(cls, automation: Automation | dict[str, Any]) -> Literal["ui", "file"]:
        """Detect if an automation is UI-based or file-based.
        
        Args:
            automation: Automation object or dict to analyze
            
        Returns:
            "ui" if UI-based automation, "file" if file-based
        """
        # Get automation data as dict
        automation_id = automation.id if isinstance(automation, Automation) else automation.get("id")
        
        # Check if ID matches UI pattern
        if automation_id and cls.is_ui_id(automation_id):
            return "ui"
        
        return "file"
    
    @classmethod
    def detect_storage_type(cls, automation: Automation | dict[str, Any]) -> StorageType:
        """Detect the storage type of an automation.
        
        Args:
            automation: Automation object or dict to analyze
            
        Returns:
            StorageType enum value
        """
        type_str = cls.detect_automation_type(automation)
        return StorageType.UI if type_str == "ui" else StorageType.FILE
    
    @classmethod
    def is_ui_id(cls, automation_id: str) -> bool:
        """Check if an automation ID follows UI format (32-char hex).
        
        Args:
            automation_id: The automation ID to check
            
        Returns:
            True if UI-style ID, False otherwise
        """
        if not automation_id:
            return False
        return bool(cls.UI_ID_PATTERN.match(automation_id))
    
    @classmethod
    def generate_ui_id(cls) -> str:
        """Generate a new UI-style automation ID (32-char hex).
        
        Returns:
            A new 32-character hexadecimal ID
        """
        import uuid
        return uuid.uuid4().hex
    
    @classmethod
    def validate_id_format(cls, automation_id: str, storage_type: Literal["ui", "file"]) -> bool:
        """Validate if an automation ID is appropriate for the storage type.
        
        Args:
            automation_id: The automation ID to validate
            storage_type: The target storage type
            
        Returns:
            True if ID is valid for the storage type
        """
        if storage_type == "ui":
            # UI automations must have 32-char hex IDs
            return cls.is_ui_id(automation_id) if automation_id else False
        else:  # file
            # File automations can have any ID or no ID
            # But should NOT have UI-style IDs
            return not cls.is_ui_id(automation_id) if automation_id else True
    
    @classmethod
    def analyze_automation_set(cls, automations: list[Automation | dict[str, Any]]) -> dict[str, Any]:
        """Analyze a set of automations to determine storage type distribution.
        
        Args:
            automations: List of automations to analyze
            
        Returns:
            Analysis results with counts and percentages
        """
        ui_count = 0
        file_count = 0
        ui_ids = []
        file_ids = []
        
        for automation in automations:
            automation_type = cls.detect_automation_type(automation)
            
            # Get ID
            automation_id = automation.id if isinstance(automation, Automation) else automation.get("id")
            
            if automation_type == "ui":
                ui_count += 1
                if automation_id:
                    ui_ids.append(automation_id)
            else:
                file_count += 1
                if automation_id:
                    file_ids.append(automation_id)
        
        total = ui_count + file_count
        
        return {
            "total": total,
            "ui_count": ui_count,
            "file_count": file_count,
            "ui_percentage": (ui_count / total * 100) if total > 0 else 0,
            "file_percentage": (file_count / total * 100) if total > 0 else 0,
            "ui_ids": ui_ids,
            "file_ids": file_ids,
            "mixed_storage": ui_count > 0 and file_count > 0,
        }