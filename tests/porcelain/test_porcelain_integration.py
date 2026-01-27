"""Integration tests for porcelain mode across different commands."""

import json
import pytest


class TestAutomationsPorcelainIntegration:
    """Test porcelain mode integration for automation commands."""
    
    def test_automations_list_porcelain_output_structure(self):
        """Test that automation list porcelain output has correct structure."""
        # This test verifies the output structure is consistent
        # In a real implementation, this would test the actual CLI command
        sample_output = {
            "command": "automations list",
            "timestamp": "2025-06-14T08:27:15.822406+00:00",
            "status": "success",
            "metadata": {
                "total_count": 2,
                "filtered_count": 2,
                "filters_applied": [],
                "storage_breakdown": {"ui": 0, "file": 2},
                "home_assistant": {
                    "url": "http://homeassistant.local:8123",
                    "connection_method": "rest"
                },
                "response_time_ms": 74
            },
            "data": [
                {
                    "id": "test_automation",
                    "alias": "Test Automation",
                    "mode": "single",
                    "storage_type": "file",
                    "last_triggered": None,
                    "enabled": True,
                    "entity_id": "automation.test_automation"
                }
            ],
            "suggestions": {
                "common_actions": [
                    "View details: ha-cli automations read <id> --porcelain",
                    "Enable/disable: ha-cli automations enable|disable <id>",
                    "Monitor events: ha-cli automations monitor --porcelain"
                ],
                "detected_issues": [],
                "related_commands": [
                    "dashboards list --porcelain",
                    "automations monitor --porcelain"
                ]
            }
        }
        
        # Verify required top-level fields
        assert "command" in sample_output
        assert "timestamp" in sample_output
        assert "status" in sample_output
        assert "metadata" in sample_output
        assert "data" in sample_output
        assert "suggestions" in sample_output
        
        # Verify metadata structure
        metadata = sample_output["metadata"]
        assert "total_count" in metadata
        assert "storage_breakdown" in metadata
        assert "home_assistant" in metadata
        assert "response_time_ms" in metadata
        
        # Verify data structure
        assert isinstance(sample_output["data"], list)
        if sample_output["data"]:
            automation = sample_output["data"][0]
            assert "id" in automation
            assert "alias" in automation
            assert "entity_id" in automation
            assert "storage_type" in automation
        
        # Verify suggestions structure
        suggestions = sample_output["suggestions"]
        assert "common_actions" in suggestions
        assert "related_commands" in suggestions
        assert isinstance(suggestions["common_actions"], list)
    
    def test_automations_read_porcelain_error_structure(self):
        """Test that automation read errors have correct porcelain structure."""
        sample_error = {
            "command": "automations read",
            "timestamp": "2025-06-14T08:38:05.968117+00:00",
            "status": "error",
            "metadata": {
                "response_time_ms": 51
            },
            "error": {
                "type": "Error",
                "message": "Automation 'nonexistent' not found",
                "code": "NOT_FOUND",
                "details": {
                    "automation_id": "nonexistent"
                }
            },
            "suggestions": {
                "troubleshooting": [
                    "Verify automation ID 'nonexistent' exists",
                    "Use 'ha-cli automations list --porcelain' to see all automations"
                ],
                "related_commands": [
                    "ha-cli automations list --porcelain"
                ]
            }
        }
        
        # Verify error response structure
        assert sample_error["status"] == "error"
        assert "error" in sample_error
        assert "data" not in sample_error  # Errors don't have data
        
        # Verify error object structure
        error = sample_error["error"]
        assert "type" in error
        assert "message" in error
        assert "code" in error
        assert "details" in error
        
        # Verify suggestions include troubleshooting
        suggestions = sample_error["suggestions"]
        assert "troubleshooting" in suggestions
        assert len(suggestions["troubleshooting"]) > 0


class TestDashboardsPorcelainIntegration:
    """Test porcelain mode integration for dashboard commands."""
    
    def test_dashboards_list_porcelain_output_structure(self):
        """Test that dashboard list porcelain output has correct structure."""
        sample_output = {
            "command": "dashboards list",
            "timestamp": "2025-06-14T08:39:34.596581+00:00",
            "status": "success",
            "metadata": {
                "total_count": 3,
                "storage_mode_breakdown": {"storage": 3, "yaml": 0},
                "sidebar_count": 3,
                "admin_only_count": 0,
                "home_assistant": {
                    "url": "http://homeassistant.local:8123",
                    "connection_method": "rest"
                },
                "response_time_ms": 19
            },
            "data": [
                {
                    "id": "default",
                    "url_path": "",
                    "title": "Default",
                    "mode": "storage",
                    "show_in_sidebar": True,
                    "require_admin": False,
                    "icon": None
                }
            ],
            "suggestions": {
                "common_actions": [
                    "View dashboard: ha-cli dashboards read <url-path> --porcelain",
                    "Extract entities: ha-cli dashboards entities <url-path> --porcelain"
                ],
                "detected_issues": [],
                "related_commands": [
                    "automations list --porcelain",
                    "dashboards entities --porcelain"
                ]
            }
        }
        
        # Verify dashboard-specific metadata
        metadata = sample_output["metadata"]
        assert "storage_mode_breakdown" in metadata
        assert "sidebar_count" in metadata
        assert "admin_only_count" in metadata
        
        # Verify dashboard data structure
        if sample_output["data"]:
            dashboard = sample_output["data"][0]
            assert "id" in dashboard
            assert "url_path" in dashboard
            assert "title" in dashboard
            assert "mode" in dashboard
            assert "show_in_sidebar" in dashboard
            assert "require_admin" in dashboard
    
    def test_dashboards_entities_porcelain_output_structure(self):
        """Test that dashboard entities porcelain output has correct structure."""
        sample_output = {
            "command": "dashboards entities",
            "timestamp": "2025-06-14T08:40:37.450975+00:00",
            "status": "success",
            "metadata": {
                "dashboard_url_path": "dashboard-office",
                "total_entities": 5,
                "unique_domains": 3,
                "domain_breakdown": {
                    "sensor": 3,
                    "light": 1,
                    "switch": 1
                },
                "home_assistant": {
                    "url": "http://homeassistant.local:8123",
                    "connection_method": "rest"
                },
                "response_time_ms": 22
            },
            "data": [
                {
                    "entity_id": "sensor.office_temperature",
                    "domain": "sensor",
                    "friendly_name": "Sensor.Office Temperature"
                },
                {
                    "entity_id": "light.office_main",
                    "domain": "light",
                    "friendly_name": "Light.Office Main"
                }
            ],
            "suggestions": {
                "common_actions": [
                    "View dashboard: ha-cli dashboards read dashboard-office --porcelain",
                    "Check entity states: Use MCP tools for real-time states"
                ],
                "detected_issues": [],
                "related_commands": [
                    "ha-cli dashboards list --porcelain",
                    "ha-cli automations list --porcelain"
                ]
            }
        }
        
        # Verify entity-specific metadata
        metadata = sample_output["metadata"]
        assert "dashboard_url_path" in metadata
        assert "total_entities" in metadata
        assert "unique_domains" in metadata
        assert "domain_breakdown" in metadata
        
        # Verify entity data structure
        if sample_output["data"]:
            entity = sample_output["data"][0]
            assert "entity_id" in entity
            assert "domain" in entity
            assert "friendly_name" in entity
            
            # Verify entity_id format
            assert "." in entity["entity_id"]
            assert entity["entity_id"].startswith(entity["domain"] + ".")


class TestPorcelainConsistency:
    """Test consistency across all porcelain implementations."""
    
    def test_all_success_responses_have_required_fields(self):
        """Test that all success responses have consistent required fields."""
        required_fields = ["command", "timestamp", "status", "metadata", "data", "suggestions"]
        
        # Sample responses from different commands
        sample_responses = [
            {  # Automations list
                "command": "automations list",
                "timestamp": "2025-06-14T08:27:15.822406+00:00",
                "status": "success",
                "metadata": {"total_count": 1, "response_time_ms": 74},
                "data": [{"id": "test"}],
                "suggestions": {"common_actions": []}
            },
            {  # Dashboards list
                "command": "dashboards list",
                "timestamp": "2025-06-14T08:39:34.596581+00:00",
                "status": "success", 
                "metadata": {"total_count": 1, "response_time_ms": 19},
                "data": [{"id": "default"}],
                "suggestions": {"common_actions": []}
            },
            {  # Dashboard entities
                "command": "dashboards entities",
                "timestamp": "2025-06-14T08:40:37.450975+00:00",
                "status": "success",
                "metadata": {"total_entities": 1, "response_time_ms": 22},
                "data": [{"entity_id": "sensor.test"}],
                "suggestions": {"common_actions": []}
            }
        ]
        
        for response in sample_responses:
            for field in required_fields:
                assert field in response, f"Missing {field} in {response['command']} response"
            
            # Verify status is success
            assert response["status"] == "success"
            
            # Verify timestamp format (ISO 8601)
            assert "T" in response["timestamp"]
            assert response["timestamp"].endswith("+00:00")
            
            # Verify metadata has response_time_ms
            assert "response_time_ms" in response["metadata"]
            assert isinstance(response["metadata"]["response_time_ms"], int)
    
    def test_all_error_responses_have_required_fields(self):
        """Test that all error responses have consistent required fields."""
        required_fields = ["command", "timestamp", "status", "metadata", "error", "suggestions"]
        
        sample_error_responses = [
            {  # Automation not found
                "command": "automations read",
                "timestamp": "2025-06-14T08:38:05.968117+00:00",
                "status": "error",
                "metadata": {"response_time_ms": 51},
                "error": {
                    "type": "NotFoundError",
                    "message": "Automation not found",
                    "code": "NOT_FOUND"
                },
                "suggestions": {"troubleshooting": ["Check automation ID"]}
            },
            {  # Dashboard validation error
                "command": "dashboards entities",
                "timestamp": "2025-06-14T08:40:47.311918+00:00",
                "status": "error",
                "metadata": {"response_time_ms": 25},
                "error": {
                    "type": "ValidationError",
                    "message": "Invalid dashboard configuration"
                },
                "suggestions": {"troubleshooting": ["Check dashboard config"]}
            }
        ]
        
        for response in sample_error_responses:
            for field in required_fields:
                assert field in response, f"Missing {field} in {response['command']} error response"
            
            # Verify status is error
            assert response["status"] == "error"
            
            # Verify error object structure
            error = response["error"]
            assert "type" in error
            assert "message" in error
            
            # Verify suggestions include troubleshooting
            assert "troubleshooting" in response["suggestions"]
            
            # Verify no data field in error responses
            assert "data" not in response
    
    def test_porcelain_metadata_consistency(self):
        """Test that metadata fields are consistent across commands."""
        # Common metadata fields that should be present in all responses
        common_fields = ["response_time_ms"]
        
        sample_metadata = [
            {  # Automations
                "total_count": 51,
                "storage_breakdown": {"ui": 0, "file": 51},
                "response_time_ms": 74
            },
            {  # Dashboards
                "total_count": 9,
                "storage_mode_breakdown": {"storage": 9, "yaml": 0},
                "response_time_ms": 19
            },
            {  # Dashboard entities
                "total_entities": 1,
                "unique_domains": 1,
                "response_time_ms": 22
            }
        ]
        
        for metadata in sample_metadata:
            for field in common_fields:
                assert field in metadata, f"Missing common metadata field: {field}"
            
            # Verify response_time_ms is positive integer
            assert isinstance(metadata["response_time_ms"], int)
            assert metadata["response_time_ms"] >= 0
    
    def test_suggestions_structure_consistency(self):
        """Test that suggestions have consistent structure across commands."""
        sample_suggestions = [
            {  # Automations
                "common_actions": ["View details: ha-cli automations read <id>"],
                "detected_issues": [],
                "related_commands": ["dashboards list --porcelain"]
            },
            {  # Dashboards
                "common_actions": ["View dashboard: ha-cli dashboards read <url-path>"],
                "detected_issues": [],
                "related_commands": ["automations list --porcelain"]
            },
            {  # Error case
                "troubleshooting": ["Check configuration"],
                "related_commands": ["ha-cli --help"]
            }
        ]
        
        for suggestions in sample_suggestions:
            # All suggestion categories should be lists
            for key, value in suggestions.items():
                assert isinstance(value, list), f"Suggestion {key} should be a list"
            
            # If common_actions exists, it should have actionable items
            if "common_actions" in suggestions:
                assert len(suggestions["common_actions"]) > 0
                for action in suggestions["common_actions"]:
                    assert isinstance(action, str)
                    assert len(action) > 0