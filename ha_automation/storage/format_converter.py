"""Convert between singular/plural automation formats."""

from copy import deepcopy
from typing import Any


class FormatConverter:
    """Convert between file-based (singular) and UI-style (plural) automation formats."""
    
    SINGULAR_TO_PLURAL = {
        "trigger": "triggers",
        "condition": "conditions",
        "action": "actions",
    }
    
    PLURAL_TO_SINGULAR = {
        "triggers": "trigger",
        "conditions": "condition", 
        "actions": "action",
    }
    
    @classmethod
    def to_plural_format(cls, automation_data: dict[str, Any]) -> dict[str, Any]:
        """Convert from singular format (file-based) to plural format (UI-style).
        
        Args:
            automation_data: Automation data in singular format
            
        Returns:
            Automation data in plural format
        """
        result = deepcopy(automation_data)
        
        # Convert singular to plural
        for singular, plural in cls.SINGULAR_TO_PLURAL.items():
            if singular in result:
                result[plural] = result.pop(singular)
        
        return result
    
    @classmethod
    def to_singular_format(cls, automation_data: dict[str, Any]) -> dict[str, Any]:
        """Convert from plural format (UI-style) to singular format (file-based).
        
        Args:
            automation_data: Automation data in plural format
            
        Returns:
            Automation data in singular format
        """
        result = deepcopy(automation_data)
        
        # Convert plural to singular
        for plural, singular in cls.PLURAL_TO_SINGULAR.items():
            if plural in result:
                result[singular] = result.pop(plural)
        
        return result
    
    @classmethod
    def is_plural_format(cls, automation_data: dict[str, Any]) -> bool:
        """Check if automation data is in plural format (UI-style).
        
        Args:
            automation_data: Automation data to check
            
        Returns:
            True if plural format, False if singular format
        """
        # Check if any plural keys exist
        return any(key in automation_data for key in cls.PLURAL_TO_SINGULAR.keys())
    
    @classmethod
    def is_singular_format(cls, automation_data: dict[str, Any]) -> bool:
        """Check if automation data is in singular format (file-based).
        
        Args:
            automation_data: Automation data to check
            
        Returns:
            True if singular format, False if plural format
        """
        # Check if any singular keys exist
        return any(key in automation_data for key in cls.SINGULAR_TO_PLURAL.keys())
    
    @classmethod
    def normalize_format(cls, automation_data: dict[str, Any], target_format: str = "singular") -> dict[str, Any]:
        """Normalize automation data to the specified format.
        
        Args:
            automation_data: Automation data to normalize
            target_format: Target format ("singular" or "plural")
            
        Returns:
            Normalized automation data
            
        Raises:
            ValueError: If target_format is not "singular" or "plural"
        """
        if target_format not in ("singular", "plural"):
            raise ValueError(f"Invalid target format: {target_format}")
        
        if target_format == "singular":
            if cls.is_plural_format(automation_data):
                return cls.to_singular_format(automation_data)
        else:  # plural
            if cls.is_singular_format(automation_data):
                return cls.to_plural_format(automation_data)
        
        return deepcopy(automation_data)