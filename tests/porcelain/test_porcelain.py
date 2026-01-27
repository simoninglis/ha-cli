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
            "http://homeassistant.local:8123",
            "websocket",
            "2024.12.0"
        )
        
        assert metadata["url"] == "http://homeassistant.local:8123"
        assert metadata["connection_method"] == "websocket"
        assert metadata["version"] == "2024.12.0"
    
    def test_home_assistant_metadata_no_version(self):
        """Test Home Assistant metadata without version."""
        metadata = create_home_assistant_metadata(
            "http://homeassistant.local:8123",
            "rest"
        )
        
        assert metadata["url"] == "http://homeassistant.local:8123"
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
                "http://homeassistant.local:8123",
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
        assert response_data["metadata"]["home_assistant"]["url"] == "http://homeassistant.local:8123"
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


class TestCleanJSONEncoder:
    """Tests for CleanJSONEncoder class."""

    def test_removes_control_characters(self):
        """Test that control characters are removed from strings."""
        from ha_cli.common.porcelain import CleanJSONEncoder

        encoder = CleanJSONEncoder()
        # String with control characters (bell, backspace, etc.)
        data = {"text": "hello\x00\x07\x08world"}

        result = encoder.encode(data)
        parsed = json.loads(result)

        assert parsed["text"] == "helloworld"

    def test_preserves_valid_whitespace(self):
        """Test that tab, newline, carriage return are preserved."""
        from ha_cli.common.porcelain import CleanJSONEncoder

        encoder = CleanJSONEncoder()
        data = {"text": "line1\nline2\tindented"}

        result = encoder.encode(data)
        parsed = json.loads(result)

        assert "\n" in parsed["text"]
        assert "\t" in parsed["text"]

    def test_sanitizes_nested_structures(self):
        """Test that nested structures are sanitized."""
        from ha_cli.common.porcelain import CleanJSONEncoder

        encoder = CleanJSONEncoder()
        data = {
            "outer": {
                "inner": "text\x00with\x07control"
            },
            "list": ["item1\x00", "item2\x08"]
        }

        result = encoder.encode(data)
        parsed = json.loads(result)

        assert parsed["outer"]["inner"] == "textwithcontrol"
        assert parsed["list"][0] == "item1"
        assert parsed["list"][1] == "item2"


class TestAnalyzeAutomationComplexity:
    """Tests for analyze_automation_complexity function."""

    def test_simple_automation(self):
        """Test complexity analysis for simple automation."""
        from ha_cli.common.porcelain import analyze_automation_complexity

        automation = {
            "trigger": [{"platform": "state"}],
            "condition": [],
            "action": [{"service": "light.turn_on"}]
        }

        result = analyze_automation_complexity(automation)

        assert result["level"] == "simple"
        assert result["score"] <= 5
        assert len(result["factors"]) == 0

    def test_complex_automation(self):
        """Test complexity analysis for complex automation."""
        from ha_cli.common.porcelain import analyze_automation_complexity

        automation = {
            "trigger": [{"platform": "state"}] * 5,
            "condition": [{"condition": "state"}] * 4,
            "action": [{"service": "light.turn_on"}] * 8
        }

        result = analyze_automation_complexity(automation)

        assert result["level"] in ["complex", "very_complex"]
        assert result["score"] > 15
        assert len(result["factors"]) > 0

    def test_complexity_factors_reported(self):
        """Test that complexity factors are properly reported."""
        from ha_cli.common.porcelain import analyze_automation_complexity

        automation = {
            "trigger": [{"platform": "state"}] * 5,
            "condition": [{"condition": "state"}] * 3,
            "action": [{"service": "light.turn_on"}] * 10
        }

        result = analyze_automation_complexity(automation)

        factors_text = " ".join(result["factors"])
        assert "triggers" in factors_text.lower() or "actions" in factors_text.lower()

    def test_optimization_suggestions_for_complex(self):
        """Test that complex automations get optimization suggestions."""
        from ha_cli.common.porcelain import analyze_automation_complexity

        automation = {
            "trigger": [{"platform": "state"}] * 6,
            "condition": [{"condition": "state"}] * 5,
            "action": [{"service": "light.turn_on"}] * 10
        }

        result = analyze_automation_complexity(automation)

        assert len(result["optimizations"]) > 0


class TestExtractEntityReferences:
    """Tests for extract_entity_references function."""

    def test_extract_from_triggers(self):
        """Test extracting entity IDs from triggers."""
        from ha_cli.common.porcelain import extract_entity_references

        automation = {
            "trigger": [
                {"platform": "state", "entity_id": "light.living_room"}
            ],
            "condition": [],
            "action": []
        }

        result = extract_entity_references(automation)

        assert "light.living_room" in result["referenced"]
        assert "light.living_room" in result["triggers"]

    def test_extract_from_actions(self):
        """Test extracting entity IDs from actions."""
        from ha_cli.common.porcelain import extract_entity_references

        automation = {
            "trigger": [],
            "condition": [],
            "action": [
                {"service": "light.turn_on", "entity_id": "light.bedroom"}
            ]
        }

        result = extract_entity_references(automation)

        assert "light.bedroom" in result["referenced"]
        assert "light.bedroom" in result["actions"]

    def test_extract_entity_ids_list(self):
        """Test extracting when entity_ids is a list."""
        from ha_cli.common.porcelain import extract_entity_references

        automation = {
            "trigger": [],
            "condition": [],
            "action": [
                {"service": "light.turn_on", "entity_ids": ["light.one", "light.two"]}
            ]
        }

        result = extract_entity_references(automation)

        assert "light.one" in result["referenced"]
        assert "light.two" in result["referenced"]

    def test_domain_breakdown(self):
        """Test domain breakdown of extracted entities."""
        from ha_cli.common.porcelain import extract_entity_references

        automation = {
            "trigger": [{"entity_id": "sensor.temperature"}],
            "condition": [{"entity_id": "binary_sensor.door"}],
            "action": [{"entity_id": "light.living_room"}]
        }

        result = extract_entity_references(automation)

        assert "sensor" in result["by_domain"]
        assert "binary_sensor" in result["by_domain"]
        assert "light" in result["by_domain"]

    def test_deduplicates_entities(self):
        """Test that duplicate entities are deduplicated."""
        from ha_cli.common.porcelain import extract_entity_references

        automation = {
            "trigger": [{"entity_id": "light.living_room"}],
            "condition": [],
            "action": [{"entity_id": "light.living_room"}]
        }

        result = extract_entity_references(automation)

        # Should appear only once in referenced list
        assert result["referenced"].count("light.living_room") == 1


class TestAnalyzeDashboardPerformance:
    """Tests for analyze_dashboard_performance function."""

    def test_low_entity_count_high_score(self):
        """Test that low entity count gives high performance score."""
        from ha_cli.common.porcelain import analyze_dashboard_performance

        result = analyze_dashboard_performance(10, {"light": 5, "switch": 5})

        assert result["performance_score"] == 100
        assert len(result["issues"]) == 0

    def test_high_entity_count_reduces_score(self):
        """Test that high entity count reduces performance score."""
        from ha_cli.common.porcelain import analyze_dashboard_performance

        result = analyze_dashboard_performance(120, {"light": 60, "sensor": 60})

        assert result["performance_score"] < 100
        assert any("entity count" in issue.lower() for issue in result["issues"])

    def test_many_sensors_creates_warning(self):
        """Test that many sensors create a warning."""
        from ha_cli.common.porcelain import analyze_dashboard_performance

        result = analyze_dashboard_performance(50, {"sensor": 40, "light": 10})

        assert any("sensor" in issue.lower() for issue in result["issues"])

    def test_cameras_impact_score(self):
        """Test that multiple cameras impact performance score."""
        from ha_cli.common.porcelain import analyze_dashboard_performance

        result = analyze_dashboard_performance(20, {"camera": 6, "light": 14})

        assert result["performance_score"] < 100
        assert any("camera" in issue.lower() for issue in result["issues"])

    def test_score_never_negative(self):
        """Test that performance score never goes negative."""
        from ha_cli.common.porcelain import analyze_dashboard_performance

        # Extreme case
        result = analyze_dashboard_performance(
            500, {"sensor": 200, "camera": 50, "history_stats": 50}
        )

        assert result["performance_score"] >= 0


class TestCreateWorkflowRecommendations:
    """Tests for create_workflow_recommendations function."""

    def test_automations_list_recommendations(self):
        """Test recommendations for automations list command."""
        from ha_cli.common.porcelain import create_workflow_recommendations

        context = {
            "total_count": 25,
            "storage_breakdown": {"ui": 10, "file": 15}
        }

        result = create_workflow_recommendations("automations list", context)

        assert len(result["next_steps"]) > 0
        assert len(result["workflow_sequences"]) > 0

    def test_automations_list_with_many_automations(self):
        """Test recommendations when many automations exist."""
        from ha_cli.common.porcelain import create_workflow_recommendations

        context = {
            "total_count": 75,
            "storage_breakdown": {"ui": 25, "file": 50}
        }

        result = create_workflow_recommendations("automations list", context)

        assert any("organiz" in tip.lower() for tip in result["best_practices"])

    def test_dashboards_entities_recommendations(self):
        """Test recommendations for dashboards entities command."""
        from ha_cli.common.porcelain import create_workflow_recommendations

        context = {
            "total_entities": 30,
            "domain_breakdown": {"sensor": 10, "light": 20}
        }

        result = create_workflow_recommendations("dashboards entities", context)

        assert len(result["next_steps"]) > 0
        assert len(result["integration_opportunities"]) > 0

    def test_integration_opportunities_always_present(self):
        """Test that integration opportunities are always suggested."""
        from ha_cli.common.porcelain import create_workflow_recommendations

        result = create_workflow_recommendations("automations list", {"total_count": 5})

        assert len(result["integration_opportunities"]) > 0


class TestDetectAdvancedIssues:
    """Tests for detect_advanced_issues function."""

    def test_slow_response_time_detected(self):
        """Test that slow response times are detected."""
        from ha_cli.common.porcelain import detect_advanced_issues

        metadata = {"response_time_ms": 6000}

        issues = detect_advanced_issues("test", {}, metadata)

        assert any("response time" in issue.lower() for issue in issues)

    def test_elevated_response_time_detected(self):
        """Test that elevated response times are detected."""
        from ha_cli.common.porcelain import detect_advanced_issues

        metadata = {"response_time_ms": 3000}

        issues = detect_advanced_issues("test", {}, metadata)

        assert any("response time" in issue.lower() for issue in issues)

    def test_normal_response_time_no_issue(self):
        """Test that normal response times don't create issues."""
        from ha_cli.common.porcelain import detect_advanced_issues

        metadata = {"response_time_ms": 500}

        issues = detect_advanced_issues("test", {}, metadata)

        assert not any("response time" in issue.lower() for issue in issues)

    def test_health_error_detected(self):
        """Test that health errors are detected."""
        from ha_cli.common.porcelain import detect_advanced_issues

        health_info = {"status": "error"}

        issues = detect_advanced_issues("test", {}, {}, health_info)

        assert any("health" in issue.lower() for issue in issues)

    def test_automation_antipattern_many_triggers_no_conditions(self):
        """Test detection of many triggers without conditions."""
        from ha_cli.common.porcelain import detect_advanced_issues

        automation_data = {
            "trigger": [{"platform": "state"}] * 5,
            "condition": [],
            "action": []
        }

        issues = detect_advanced_issues("automations read", automation_data, {})

        assert any("condition" in issue.lower() for issue in issues)

    def test_automation_antipattern_long_action_sequence(self):
        """Test detection of very long action sequences."""
        from ha_cli.common.porcelain import detect_advanced_issues

        automation_data = {
            "trigger": [{"platform": "state"}],
            "condition": [],
            "action": [{"service": "light.turn_on"}] * 20
        }

        issues = detect_advanced_issues("automations read", automation_data, {})

        assert any("action" in issue.lower() for issue in issues)


class TestHomeAssistantMetadataWithHealthInfo:
    """Tests for create_home_assistant_metadata with health info."""

    def test_metadata_with_health_info(self):
        """Test metadata creation with health information."""
        health_info = {
            "status": "healthy",
            "version": "2024.12.0",
            "components": 50,
            "entities": 200,
            "time_zone": "Australia/Sydney",
            "country": "AU",
            "language": "en"
        }

        result = create_home_assistant_metadata(
            "http://ha.local:8123",
            "websocket",
            health_info=health_info
        )

        assert result["version"] == "2024.12.0"
        assert result["health"]["status"] == "healthy"
        assert result["health"]["entities"] == 200
        assert result["system"]["time_zone"] == "Australia/Sydney"

    def test_metadata_with_supervisor_info(self):
        """Test metadata includes supervisor info when available."""
        health_info = {
            "status": "healthy",
            "version": "2024.12.0",
            "supervisor_version": "2024.11.0",
            "healthy": True,
            "supported": True
        }

        result = create_home_assistant_metadata(
            "http://ha.local:8123",
            "websocket",
            health_info=health_info
        )

        assert "supervisor" in result
        assert result["supervisor"]["version"] == "2024.11.0"

    def test_version_from_health_info_when_not_provided(self):
        """Test that version is taken from health_info when not provided directly."""
        health_info = {"version": "2024.12.0"}

        result = create_home_assistant_metadata(
            "http://ha.local:8123",
            "rest",
            version=None,
            health_info=health_info
        )

        assert result["version"] == "2024.12.0"


class TestStreamingPorcelainFormatter:
    """Tests for StreamingPorcelainFormatter JSONL output."""

    def test_init_sets_up_counters(self):
        """Test that initialization sets up tracking state."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")

        assert formatter.command == "events listen"
        assert formatter.event_count == 0
        assert formatter.error_count == 0
        assert formatter._summary_emitted is False
        assert formatter.start_time is not None

    def test_emit_metadata_structure(self, capsys):
        """Test metadata line has required fields."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")
        formatter.emit_metadata(event_type="deconz_event")

        output = capsys.readouterr().out.strip()
        data = json.loads(output)

        assert data["schema_version"] == 1
        assert data["type"] == "metadata"
        assert data["command"] == "events listen"
        assert "started_at" in data
        assert data["event_type"] == "deconz_event"

    def test_emit_event_structure(self, capsys):
        """Test event line has required fields."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")
        formatter.emit_event({"unique_id": "abc123", "value": 42}, event_type="deconz_event")

        output = capsys.readouterr().out.strip()
        data = json.loads(output)

        assert data["type"] == "event"
        assert "timestamp" in data
        assert data["data"]["unique_id"] == "abc123"
        assert data["data"]["value"] == 42
        assert data["event_type"] == "deconz_event"

    def test_emit_event_increments_counter(self, capsys):
        """Test event emission increments counter."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")
        assert formatter.event_count == 0

        formatter.emit_event({"key": "value1"})
        assert formatter.event_count == 1

        formatter.emit_event({"key": "value2"})
        assert formatter.event_count == 2

    def test_emit_event_without_event_type(self, capsys):
        """Test event line without optional event_type."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")
        formatter.emit_event({"data": "test"})

        output = capsys.readouterr().out.strip()
        data = json.loads(output)

        assert data["type"] == "event"
        assert "event_type" not in data

    def test_emit_error_structure(self, capsys):
        """Test error line has required fields."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")
        formatter.emit_error("Connection lost", recoverable=True, error_type="connection")

        output = capsys.readouterr().out.strip()
        data = json.loads(output)

        assert data["type"] == "error"
        assert "timestamp" in data
        assert data["message"] == "Connection lost"
        assert data["recoverable"] is True
        assert data["error_type"] == "connection"

    def test_emit_error_increments_counter(self, capsys):
        """Test error emission increments counter."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")
        assert formatter.error_count == 0

        formatter.emit_error("Error 1", recoverable=True)
        assert formatter.error_count == 1

        formatter.emit_error("Error 2", recoverable=False)
        assert formatter.error_count == 2

    def test_emit_summary_structure(self, capsys):
        """Test summary line has required fields."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter
        import time

        formatter = StreamingPorcelainFormatter("events listen")

        # Simulate some events and errors
        formatter.event_count = 5
        formatter.error_count = 2

        # Small delay to get non-zero duration
        time.sleep(0.01)

        formatter.emit_summary(exit_reason="timeout")

        output = capsys.readouterr().out.strip()
        data = json.loads(output)

        assert data["type"] == "summary"
        assert data["event_count"] == 5
        assert data["error_count"] == 2
        assert data["exit_reason"] == "timeout"
        assert "duration_seconds" in data
        assert data["duration_seconds"] >= 0
        assert "ended_at" in data

    def test_emit_summary_idempotent(self, capsys):
        """Test summary can only be emitted once."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")

        formatter.emit_summary(exit_reason="completed")
        formatter.emit_summary(exit_reason="error")  # Should be ignored
        formatter.emit_summary(exit_reason="interrupted")  # Should be ignored

        output = capsys.readouterr().out
        lines = [line for line in output.strip().split("\n") if line]

        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["exit_reason"] == "completed"  # First call wins

    def test_compact_json_separators(self, capsys):
        """Test that output uses compact JSON separators."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")
        formatter.emit_metadata(key="value")

        output = capsys.readouterr().out.strip()

        # Compact separators: no spaces after : or ,
        assert ": " not in output or '": "' in output  # Allow space in strings
        assert ", " not in output

    def test_complete_session_output(self, capsys):
        """Test complete JSONL session output."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        formatter = StreamingPorcelainFormatter("events listen")

        # Emit a complete session
        formatter.emit_metadata(event_type="state_changed")
        formatter.emit_event({"entity_id": "light.office", "old_state": "off", "new_state": "on"}, event_type="state_changed")
        formatter.emit_error("WebSocket ping timeout", recoverable=True, error_type="connection")
        formatter.emit_event({"entity_id": "light.bedroom", "old_state": "on", "new_state": "off"}, event_type="state_changed")
        formatter.emit_summary(exit_reason="count_reached")

        output = capsys.readouterr().out
        lines = [line for line in output.strip().split("\n") if line]

        assert len(lines) == 5

        # Verify each line is valid JSON
        parsed_lines = [json.loads(line) for line in lines]

        assert parsed_lines[0]["type"] == "metadata"
        assert parsed_lines[1]["type"] == "event"
        assert parsed_lines[2]["type"] == "error"
        assert parsed_lines[3]["type"] == "event"
        assert parsed_lines[4]["type"] == "summary"

        # Verify counters
        assert parsed_lines[4]["event_count"] == 2
        assert parsed_lines[4]["error_count"] == 1
        assert parsed_lines[4]["exit_reason"] == "count_reached"

    def test_exit_reason_values(self, capsys):
        """Test all valid exit reason values."""
        from ha_cli.common.porcelain import StreamingPorcelainFormatter

        exit_reasons = ["completed", "interrupted", "timeout", "count_reached", "error"]

        for reason in exit_reasons:
            formatter = StreamingPorcelainFormatter("test")
            formatter.emit_summary(exit_reason=reason)

        output = capsys.readouterr().out
        lines = [line for line in output.strip().split("\n") if line]

        assert len(lines) == 5
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["exit_reason"] == exit_reasons[i]