"""Tests for AutomationTypeDetector."""

import pytest

from ha_cli.domains.automations.models import Automation
from ha_cli.domains.automations.storage.automation_type_detector import AutomationTypeDetector


class TestAutomationTypeDetector:
    """Test automation type detection."""
    
    def test_is_ui_id(self):
        """Test UI ID pattern detection."""
        # Valid UI IDs (32-char hex)
        assert AutomationTypeDetector.is_ui_id("1234567890abcdef1234567890abcdef") is True
        assert AutomationTypeDetector.is_ui_id("abcdefabcdefabcdefabcdefabcdefab") is True
        assert AutomationTypeDetector.is_ui_id("00000000000000000000000000000000") is True
        
        # Invalid UI IDs
        assert AutomationTypeDetector.is_ui_id("1234567890abcdef1234567890abcde") is False  # 31 chars
        assert AutomationTypeDetector.is_ui_id("1234567890abcdef1234567890abcdef0") is False  # 33 chars
        assert AutomationTypeDetector.is_ui_id("1234567890abcdef1234567890ABCDEF") is False  # uppercase
        assert AutomationTypeDetector.is_ui_id("1234567890abcdef-234567890abcdef") is False  # dash
        assert AutomationTypeDetector.is_ui_id("my_custom_automation_id") is False
        assert AutomationTypeDetector.is_ui_id("") is False
        assert AutomationTypeDetector.is_ui_id(None) is False
    
    def test_generate_ui_id(self):
        """Test UI ID generation."""
        # Generate multiple IDs
        ids = [AutomationTypeDetector.generate_ui_id() for _ in range(10)]
        
        # All should be valid UI IDs
        for id_ in ids:
            assert AutomationTypeDetector.is_ui_id(id_) is True
            assert len(id_) == 32
        
        # All should be unique
        assert len(set(ids)) == len(ids)
    
    def test_detect_automation_type_with_automation(self):
        """Test detecting automation type from Automation object."""
        # UI automation
        ui_automation = Automation(
            id="1234567890abcdef1234567890abcdef",
            alias="UI Automation",
            trigger=[{"platform": "state"}],
            action=[{"service": "test"}],
        )
        assert AutomationTypeDetector.detect_automation_type(ui_automation) == "ui"
        
        # File automation with custom ID
        file_automation = Automation(
            id="my_custom_automation",
            alias="File Automation",
            trigger=[{"platform": "state"}],
            action=[{"service": "test"}],
        )
        assert AutomationTypeDetector.detect_automation_type(file_automation) == "file"
        
        # File automation with no ID
        no_id_automation = Automation(
            alias="No ID Automation",
            trigger=[{"platform": "state"}],
            action=[{"service": "test"}],
        )
        assert AutomationTypeDetector.detect_automation_type(no_id_automation) == "file"
    
    def test_detect_automation_type_with_dict(self):
        """Test detecting automation type from dict."""
        # UI automation dict
        ui_dict = {
            "id": "1234567890abcdef1234567890abcdef",
            "alias": "UI Automation",
            "triggers": [],
            "actions": [],
        }
        assert AutomationTypeDetector.detect_automation_type(ui_dict) == "ui"
        
        # File automation dict
        file_dict = {
            "id": "my_file_automation",
            "alias": "File Automation",
            "trigger": [],
            "action": [],
        }
        assert AutomationTypeDetector.detect_automation_type(file_dict) == "file"
        
        # No ID dict
        no_id_dict = {
            "alias": "No ID",
            "trigger": [],
            "action": [],
        }
        assert AutomationTypeDetector.detect_automation_type(no_id_dict) == "file"
    
    def test_validate_id_format(self):
        """Test ID format validation for storage types."""
        ui_id = "1234567890abcdef1234567890abcdef"
        file_id = "my_custom_automation"
        
        # UI storage validation
        assert AutomationTypeDetector.validate_id_format(ui_id, "ui") is True
        assert AutomationTypeDetector.validate_id_format(file_id, "ui") is False
        assert AutomationTypeDetector.validate_id_format(None, "ui") is False
        assert AutomationTypeDetector.validate_id_format("", "ui") is False
        
        # File storage validation
        assert AutomationTypeDetector.validate_id_format(file_id, "file") is True
        assert AutomationTypeDetector.validate_id_format(ui_id, "file") is False  # UI IDs not allowed in file
        assert AutomationTypeDetector.validate_id_format(None, "file") is True  # No ID is OK for file
        assert AutomationTypeDetector.validate_id_format("", "file") is True  # Empty ID is OK for file
    
    def test_analyze_automation_set(self):
        """Test analyzing a set of automations."""
        automations = [
            # UI automations
            Automation(
                id="1234567890abcdef1234567890abcdef",
                alias="UI 1",
                trigger=[],
                action=[],
            ),
            Automation(
                id="abcdefabcdefabcdefabcdefabcdefab",
                alias="UI 2",
                trigger=[],
                action=[],
            ),
            # File automations
            Automation(
                id="file_automation_1",
                alias="File 1",
                trigger=[],
                action=[],
            ),
            Automation(
                id="file_automation_2",
                alias="File 2",
                trigger=[],
                action=[],
            ),
            Automation(
                alias="File 3 (no ID)",
                trigger=[],
                action=[],
            ),
        ]
        
        analysis = AutomationTypeDetector.analyze_automation_set(automations)
        
        assert analysis["total"] == 5
        assert analysis["ui_count"] == 2
        assert analysis["file_count"] == 3
        assert analysis["ui_percentage"] == 40.0
        assert analysis["file_percentage"] == 60.0
        assert len(analysis["ui_ids"]) == 2
        assert len(analysis["file_ids"]) == 2  # One has no ID
        assert analysis["mixed_storage"] is True
    
    def test_analyze_empty_set(self):
        """Test analyzing empty automation set."""
        analysis = AutomationTypeDetector.analyze_automation_set([])
        
        assert analysis["total"] == 0
        assert analysis["ui_count"] == 0
        assert analysis["file_count"] == 0
        assert analysis["ui_percentage"] == 0
        assert analysis["file_percentage"] == 0
        assert analysis["ui_ids"] == []
        assert analysis["file_ids"] == []
        assert analysis["mixed_storage"] is False
    
    def test_analyze_all_ui_automations(self):
        """Test analyzing set with only UI automations."""
        automations = [
            {"id": "1234567890abcdef1234567890abcdef", "alias": "UI 1"},
            {"id": "abcdefabcdefabcdefabcdefabcdefab", "alias": "UI 2"},
        ]
        
        analysis = AutomationTypeDetector.analyze_automation_set(automations)
        
        assert analysis["total"] == 2
        assert analysis["ui_count"] == 2
        assert analysis["file_count"] == 0
        assert analysis["ui_percentage"] == 100.0
        assert analysis["file_percentage"] == 0.0
        assert analysis["mixed_storage"] is False
    
    def test_analyze_all_file_automations(self):
        """Test analyzing set with only file automations."""
        automations = [
            {"id": "file_1", "alias": "File 1"},
            {"id": "file_2", "alias": "File 2"},
            {"alias": "File 3"},  # No ID
        ]
        
        analysis = AutomationTypeDetector.analyze_automation_set(automations)
        
        assert analysis["total"] == 3
        assert analysis["ui_count"] == 0
        assert analysis["file_count"] == 3
        assert analysis["ui_percentage"] == 0.0
        assert analysis["file_percentage"] == 100.0
        assert analysis["mixed_storage"] is False