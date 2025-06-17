"""Tests for porcelain mode functionality."""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock

from ha_cli.common.porcelain import (
    PorcelainFormatter,
    PorcelainMetadata,
    PorcelainSuggestions,
    PorcelainError,
    PorcelainResponse,
    create_automation_suggestions,
    create_dashboard_suggestions,
    create_home_assistant_metadata,
)
from ha_cli.common.exceptions import HAAutomationError


class TestPorcelainModels:
    """Test Pydantic models for porcelain responses."""
    
    def test_porcelain_metadata_basic(self):
        """Test basic metadata creation."""
        metadata = PorcelainMetadata(
            total_count=10,
            filtered_count=5,
            filters_applied=["storage=file"]
        )
        assert metadata.total_count == 10
        assert metadata.filtered_count == 5
        assert metadata.filters_applied == ["storage=file"]
    
    def test_porcelain_metadata_extra_fields(self):
        """Test that extra fields are allowed in metadata."""
        metadata = PorcelainMetadata(
            total_count=10,
            custom_field="test_value"
        )
        assert metadata.total_count == 10
        # Extra fields should be preserved
        data = metadata.model_dump()
        assert data["custom_field"] == "test_value"
    
    def test_porcelain_suggestions_basic(self):
        """Test basic suggestions creation."""
        suggestions = PorcelainSuggestions(
            common_actions=["action1", "action2"],
            detected_issues=["issue1"],
            related_commands=["command1"]
        )
        assert len(suggestions.common_actions) == 2
        assert len(suggestions.detected_issues) == 1
        assert len(suggestions.related_commands) == 1
    
    def test_porcelain_error(self):
        """Test error object creation."""
        error = PorcelainError(
            type="AuthenticationError",
            message="Invalid token",
            code="AUTH_001",
            details={"endpoint": "/api/test"}
        )
        assert error.type == "AuthenticationError"
        assert error.message == "Invalid token"
        assert error.code == "AUTH_001"
        assert error.details["endpoint"] == "/api/test"
    
    def test_porcelain_response_success(self):
        """Test complete success response."""
        metadata = PorcelainMetadata(total_count=5)
        suggestions = PorcelainSuggestions(common_actions=["test"])
        
        response = PorcelainResponse(
            command="test command",
            timestamp="2025-06-14T10:00:00Z",
            status="success",
            metadata=metadata,
            data=[{"id": "test"}],
            suggestions=suggestions
        )
        
        assert response.command == "test command"
        assert response.status == "success"
        assert response.data == [{"id": "test"}]
        assert response.error is None
    
    def test_porcelain_response_error(self):
        """Test complete error response."""
        error = PorcelainError(type="TestError", message="Test message")
        suggestions = PorcelainSuggestions(troubleshooting=["Fix it"])
        
        response = PorcelainResponse(
            command="test command",
            timestamp="2025-06-14T10:00:00Z",
            status="error",
            error=error,
            suggestions=suggestions
        )
        
        assert response.command == "test command"
        assert response.status == "error"
        assert response.error.type == "TestError"
        assert response.data is None


class TestPorcelainFormatter:
    """Test the PorcelainFormatter utility class."""
    
    def test_formatter_initialization(self):
        """Test formatter initialization."""
        formatter = PorcelainFormatter("test command")
        assert formatter.command == "test command"
        assert formatter.start_time > 0
    
    def test_success_response_basic(self):
        """Test basic success response generation."""
        formatter = PorcelainFormatter("test command")
        data = [{"id": "test1"}, {"id": "test2"}]
        
        output = formatter.success(data)
        
        # Parse JSON output
        response_data = json.loads(output)
        
        assert response_data["command"] == "test command"
        assert response_data["status"] == "success"
        assert response_data["data"] == data
        assert "timestamp" in response_data
        assert "metadata" in response_data
        assert "response_time_ms" in response_data["metadata"]
    
    def test_success_response_with_metadata(self):
        """Test success response with custom metadata."""
        formatter = PorcelainFormatter("test command")
        data = {"result": "success"}
        metadata = {"total_count": 10, "custom_field": "value"}
        suggestions = {"common_actions": ["action1"]}
        
        output = formatter.success(data, metadata, suggestions)
        response_data = json.loads(output)
        
        assert response_data["metadata"]["total_count"] == 10
        assert response_data["metadata"]["custom_field"] == "value"
        assert response_data["suggestions"]["common_actions"] == ["action1"]
    
    def test_error_response_from_exception(self):
        """Test error response from standard exception."""
        formatter = PorcelainFormatter("test command")
        error = ValueError("Test error message")
        
        output = formatter.error(error)
        response_data = json.loads(output)
        
        assert response_data["command"] == "test command"
        assert response_data["status"] == "error"
        assert response_data["error"]["type"] == "ValueError"
        assert response_data["error"]["message"] == "Test error message"
        assert "troubleshooting" in response_data["suggestions"]
    
    def test_error_response_from_ha_error(self):
        """Test error response from HAAutomationError."""
        formatter = PorcelainFormatter("test command")
        error = HAAutomationError("Test HA error", details={"endpoint": "/api/test"})
        
        output = formatter.error(error, error_code="HA_001")
        response_data = json.loads(output)
        
        assert response_data["error"]["type"] == "HAAutomationError"
        assert response_data["error"]["message"] == "Test HA error"
        assert response_data["error"]["code"] == "HA_001"
        assert response_data["error"]["details"]["endpoint"] == "/api/test"
    
    def test_error_response_from_string(self):
        """Test error response from string message."""
        formatter = PorcelainFormatter("test command")
        
        output = formatter.error("Simple error message")
        response_data = json.loads(output)
        
        assert response_data["error"]["type"] == "Error"
        assert response_data["error"]["message"] == "Simple error message"
    
    def test_default_error_suggestions(self):
        """Test that default error suggestions are provided."""
        formatter = PorcelainFormatter("test command")
        
        # Test AuthenticationError suggestions
        auth_error = HAAutomationError("Auth failed")
        auth_error.__class__.__name__ = "AuthenticationError"
        
        output = formatter.error(auth_error)
        response_data = json.loads(output)
        
        suggestions = response_data["suggestions"]["troubleshooting"]
        assert any("token" in s.lower() for s in suggestions)
        assert any("home assistant" in s.lower() for s in suggestions)
    
    def test_custom_error_suggestions(self):
        """Test custom error suggestions override defaults."""
        formatter = PorcelainFormatter("test command")
        custom_suggestions = {
            "troubleshooting": ["Custom fix 1", "Custom fix 2"],
            "related_commands": ["custom command"]
        }
        
        output = formatter.error("Test error", suggestions=custom_suggestions)
        response_data = json.loads(output)
        
        assert response_data["suggestions"]["troubleshooting"] == ["Custom fix 1", "Custom fix 2"]
        assert response_data["suggestions"]["related_commands"] == ["custom command"]


class TestSuggestionHelpers:
    """Test suggestion helper functions."""
    
    def test_automation_suggestions_normal_count(self):
        """Test automation suggestions for normal automation count."""
        suggestions = create_automation_suggestions(25, {"ui": 5, "file": 20})
        
        assert "View details:" in suggestions["common_actions"][0]
        assert "Enable/disable:" in suggestions["common_actions"][1]
        assert "Monitor events:" in suggestions["common_actions"][2]
        assert "dashboards list" in suggestions["related_commands"][0]
        assert len(suggestions["detected_issues"]) == 0
    
    def test_automation_suggestions_zero_count(self):
        """Test automation suggestions when no automations exist."""
        suggestions = create_automation_suggestions(0, {"ui": 0, "file": 0})
        
        assert "No automations found" in suggestions["detected_issues"]
        assert "Create automation:" in suggestions["common_actions"][0]
        assert "Check Home Assistant" in suggestions["common_actions"][1]
    
    def test_automation_suggestions_large_count(self):
        """Test automation suggestions for large automation count."""
        suggestions = create_automation_suggestions(150, {"ui": 50, "file": 100})
        
        assert any("Large number" in issue for issue in suggestions["detected_issues"])
        assert any("performance" in issue for issue in suggestions["detected_issues"])
        assert "reviewing and optimizing" in suggestions["common_actions"][0]
    
    def test_automation_suggestions_ui_only(self):
        """Test suggestions when only UI automations exist."""
        suggestions = create_automation_suggestions(10, {"ui": 10, "file": 0})
        
        actions = " ".join(suggestions["common_actions"])
        assert "migrating UI automations" in actions or "version control" in actions
    
    def test_dashboard_suggestions_normal_count(self):
        """Test dashboard suggestions for normal count."""
        suggestions = create_dashboard_suggestions(5)
        
        assert "View dashboard:" in suggestions["common_actions"][0]
        assert "Extract entities:" in suggestions["common_actions"][1]
        assert "Backup dashboard:" in suggestions["common_actions"][2]
        assert len(suggestions["detected_issues"]) == 0
    
    def test_dashboard_suggestions_zero_count(self):
        """Test dashboard suggestions when no dashboards exist."""
        suggestions = create_dashboard_suggestions(0)
        
        assert "No dashboards found" in suggestions["detected_issues"]
        assert "Create dashboard:" in suggestions["common_actions"][0]
    
    def test_home_assistant_metadata(self):
        """Test Home Assistant metadata creation."""
        metadata = create_home_assistant_metadata(
            "http://10.0.20.35:8123",
            "websocket",
            "2024.12.0"
        )
        
        assert metadata["url"] == "http://10.0.20.35:8123"
        assert metadata["connection_method"] == "websocket"
        assert metadata["version"] == "2024.12.0"
    
    def test_home_assistant_metadata_no_version(self):
        """Test Home Assistant metadata without version."""
        metadata = create_home_assistant_metadata(
            "http://10.0.20.35:8123",
            "rest"
        )
        
        assert metadata["url"] == "http://10.0.20.35:8123"
        assert metadata["connection_method"] == "rest"
        assert "version" not in metadata


class TestPorcelainIntegration:
    """Integration tests for porcelain mode."""
    
    def test_complete_success_workflow(self):
        """Test complete success response workflow."""
        formatter = PorcelainFormatter("automations list")
        
        # Simulate automation data
        data = [
            {
                "id": "test_automation",
                "alias": "Test Automation",
                "mode": "single",
                "storage_type": "file",
                "last_triggered": None,
                "enabled": True,
                "entity_id": "automation.test_automation"
            }
        ]
        
        metadata = {
            "total_count": 1,
            "filtered_count": 1,
            "filters_applied": [],
            "storage_breakdown": {"ui": 0, "file": 1},
            "home_assistant": create_home_assistant_metadata(
                "http://10.0.20.35:8123",
                "websocket",
                "2024.12.0"
            )
        }
        
        suggestions = create_automation_suggestions(1, {"ui": 0, "file": 1})
        
        output = formatter.success(data, metadata, suggestions)
        response_data = json.loads(output)
        
        # Verify complete structure
        assert response_data["status"] == "success"
        assert response_data["data"] == data
        assert response_data["metadata"]["total_count"] == 1
        assert response_data["metadata"]["home_assistant"]["url"] == "http://10.0.20.35:8123"
        assert len(response_data["suggestions"]["common_actions"]) > 0
    
    def test_complete_error_workflow(self):
        """Test complete error response workflow."""
        formatter = PorcelainFormatter("automations list")
        
        error = HAAutomationError(
            "Authentication failed",
            details={"endpoint": "/api/config/automation", "status_code": 401}
        )
        error.__class__.__name__ = "AuthenticationError"
        
        output = formatter.error(error, error_code="AUTH_001")
        response_data = json.loads(output)
        
        # Verify complete error structure
        assert response_data["status"] == "error"
        assert response_data["error"]["type"] == "AuthenticationError"
        assert response_data["error"]["code"] == "AUTH_001"
        assert response_data["error"]["details"]["status_code"] == 401
        assert len(response_data["suggestions"]["troubleshooting"]) > 0
        assert "token" in " ".join(response_data["suggestions"]["troubleshooting"]).lower()
    
    def test_json_serialization_edge_cases(self):
        """Test JSON serialization with edge case data."""
        formatter = PorcelainFormatter("test command")
        
        # Test with None values and empty lists
        data = {
            "null_field": None,
            "empty_list": [],
            "empty_dict": {},
            "unicode": "Test with unicode: 🏠",
            "number": 42
        }
        
        output = formatter.success(data)
        response_data = json.loads(output)
        
        # Verify all data types are preserved
        assert response_data["data"]["null_field"] is None
        assert response_data["data"]["empty_list"] == []
        assert response_data["data"]["empty_dict"] == {}
        assert response_data["data"]["unicode"] == "Test with unicode: 🏠"
        assert response_data["data"]["number"] == 42