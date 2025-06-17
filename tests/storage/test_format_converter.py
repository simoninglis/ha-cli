"""Tests for FormatConverter."""

import pytest

from ha_automation.storage.format_converter import FormatConverter


class TestFormatConverter:
    """Test automation format conversion."""
    
    def test_to_plural_format(self):
        """Test converting singular to plural format."""
        singular_data = {
            "id": "test_automation",
            "alias": "Test Automation",
            "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
            "condition": [{"condition": "state", "entity_id": "sensor.test", "state": "on"}],
            "action": [{"service": "light.turn_on", "entity_id": "light.test"}],
            "mode": "single",
        }
        
        plural_data = FormatConverter.to_plural_format(singular_data)
        
        assert "triggers" in plural_data
        assert "conditions" in plural_data
        assert "actions" in plural_data
        assert "trigger" not in plural_data
        assert "condition" not in plural_data
        assert "action" not in plural_data
        assert plural_data["triggers"] == singular_data["trigger"]
        assert plural_data["conditions"] == singular_data["condition"]
        assert plural_data["actions"] == singular_data["action"]
    
    def test_to_singular_format(self):
        """Test converting plural to singular format."""
        plural_data = {
            "id": "1234567890abcdef1234567890abcdef",
            "alias": "UI Automation",
            "triggers": [{"platform": "state", "entity_id": "sensor.test"}],
            "conditions": [{"condition": "state", "entity_id": "sensor.test", "state": "on"}],
            "actions": [{"service": "light.turn_on", "entity_id": "light.test"}],
            "mode": "single",
        }
        
        singular_data = FormatConverter.to_singular_format(plural_data)
        
        assert "trigger" in singular_data
        assert "condition" in singular_data
        assert "action" in singular_data
        assert "triggers" not in singular_data
        assert "conditions" not in singular_data
        assert "actions" not in singular_data
        assert singular_data["trigger"] == plural_data["triggers"]
        assert singular_data["condition"] == plural_data["conditions"]
        assert singular_data["action"] == plural_data["actions"]
    
    def test_is_plural_format(self):
        """Test detecting plural format."""
        plural_data = {
            "id": "test",
            "alias": "Test",
            "triggers": [],
            "actions": [],
        }
        
        singular_data = {
            "id": "test",
            "alias": "Test",
            "trigger": [],
            "action": [],
        }
        
        mixed_data = {
            "id": "test",
            "alias": "Test",
            "trigger": [],
            "actions": [],  # Mixed format
        }
        
        assert FormatConverter.is_plural_format(plural_data) is True
        assert FormatConverter.is_plural_format(singular_data) is False
        assert FormatConverter.is_plural_format(mixed_data) is True  # Has at least one plural key
    
    def test_is_singular_format(self):
        """Test detecting singular format."""
        plural_data = {
            "id": "test",
            "alias": "Test",
            "triggers": [],
            "actions": [],
        }
        
        singular_data = {
            "id": "test",
            "alias": "Test",
            "trigger": [],
            "action": [],
        }
        
        mixed_data = {
            "id": "test",
            "alias": "Test",
            "trigger": [],
            "actions": [],  # Mixed format
        }
        
        assert FormatConverter.is_singular_format(plural_data) is False
        assert FormatConverter.is_singular_format(singular_data) is True
        assert FormatConverter.is_singular_format(mixed_data) is True  # Has at least one singular key
    
    def test_normalize_format_to_singular(self):
        """Test normalizing to singular format."""
        plural_data = {
            "id": "test",
            "alias": "Test",
            "triggers": [{"platform": "state"}],
            "conditions": [{"condition": "state"}],
            "actions": [{"service": "test"}],
        }
        
        singular_data = {
            "id": "test",
            "alias": "Test",
            "trigger": [{"platform": "state"}],
            "action": [{"service": "test"}],
        }
        
        # Plural to singular
        normalized = FormatConverter.normalize_format(plural_data, "singular")
        assert "trigger" in normalized
        assert "triggers" not in normalized
        
        # Already singular
        normalized = FormatConverter.normalize_format(singular_data, "singular")
        assert "trigger" in normalized
        assert normalized == singular_data
    
    def test_normalize_format_to_plural(self):
        """Test normalizing to plural format."""
        singular_data = {
            "id": "test",
            "alias": "Test",
            "trigger": [{"platform": "state"}],
            "condition": [{"condition": "state"}],
            "action": [{"service": "test"}],
        }
        
        plural_data = {
            "id": "test",
            "alias": "Test",
            "triggers": [{"platform": "state"}],
            "actions": [{"service": "test"}],
        }
        
        # Singular to plural
        normalized = FormatConverter.normalize_format(singular_data, "plural")
        assert "triggers" in normalized
        assert "trigger" not in normalized
        
        # Already plural
        normalized = FormatConverter.normalize_format(plural_data, "plural")
        assert "triggers" in normalized
        assert normalized == plural_data
    
    def test_normalize_format_invalid_target(self):
        """Test normalize_format with invalid target."""
        data = {"id": "test", "trigger": []}
        
        with pytest.raises(ValueError, match="Invalid target format"):
            FormatConverter.normalize_format(data, "invalid")
    
    def test_format_conversion_preserves_other_fields(self):
        """Test that format conversion preserves non-trigger/condition/action fields."""
        original = {
            "id": "test_automation",
            "alias": "Test Automation",
            "description": "A test automation",
            "trigger": [{"platform": "state"}],
            "action": [{"service": "test"}],
            "mode": "queued",
            "max": 10,
            "variables": {"test": "value"},
        }
        
        # Convert to plural
        plural = FormatConverter.to_plural_format(original)
        assert plural["id"] == original["id"]
        assert plural["alias"] == original["alias"]
        assert plural["description"] == original["description"]
        assert plural["mode"] == original["mode"]
        assert plural["max"] == original["max"]
        assert plural["variables"] == original["variables"]
        
        # Convert back to singular
        singular = FormatConverter.to_singular_format(plural)
        assert singular["id"] == original["id"]
        assert singular["alias"] == original["alias"]
        assert singular["description"] == original["description"]
        assert singular["mode"] == original["mode"]
        assert singular["max"] == original["max"]
        assert singular["variables"] == original["variables"]
    
    def test_handles_missing_fields(self):
        """Test handling automations with missing optional fields."""
        # Minimal automation with no conditions
        minimal = {
            "id": "test",
            "alias": "Test",
            "trigger": [{"platform": "state"}],
            "action": [{"service": "test"}],
        }
        
        plural = FormatConverter.to_plural_format(minimal)
        assert "conditions" not in plural  # Should not add missing fields
        assert "triggers" in plural
        assert "actions" in plural
        
        # Convert back
        singular = FormatConverter.to_singular_format(plural)
        assert "condition" not in singular
        assert "trigger" in singular
        assert "action" in singular