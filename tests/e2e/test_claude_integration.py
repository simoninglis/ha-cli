"""
Integration tests for Claude Code optimization features.

These tests validate that porcelain mode provides the rich context and
intelligent suggestions needed for Claude to make better decisions.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from ha_cli.common.porcelain import (
    PorcelainFormatter,
    create_workflow_recommendations,
    detect_advanced_issues,
    analyze_automation_complexity,
    analyze_dashboard_performance,
)


class TestClaudeWorkflowOptimization:
    """Test workflow recommendations for Claude Code integration."""
    
    def test_automation_list_workflow_recommendations(self):
        """Test workflow recommendations for automation listing."""
        recommendations = create_workflow_recommendations(
            "automations list",
            {
                "total_count": 25,
                "storage_breakdown": {"ui": 5, "file": 20}
            }
        )
        
        # Should provide next steps
        assert "next_steps" in recommendations
        assert len(recommendations["next_steps"]) > 0
        assert any("ha-cli automations read" in step for step in recommendations["next_steps"])
        
        # Should suggest workflow sequences
        assert "workflow_sequences" in recommendations
        assert any("File Automation Workflow" in seq for seq in recommendations["workflow_sequences"])
        
        # Should provide best practices for reasonable automation count
        assert "best_practices" in recommendations
        
        # Should suggest integration opportunities
        assert "integration_opportunities" in recommendations
        assert any("Entity Renaming" in opp for opp in recommendations["integration_opportunities"])
    
    def test_complex_automation_workflow_recommendations(self):
        """Test workflow recommendations for complex automations."""
        recommendations = create_workflow_recommendations(
            "automations read",
            {
                "automation_id": "complex_lighting",
                "complexity": {"level": "very_complex", "score": 35},
                "entity_dependencies": {
                    "total_entities": 15,
                    "by_domain": {"light": 8, "sensor": 5, "switch": 2}
                }
            }
        )
        
        # Should provide specialized recommendations for complex automations
        assert "workflow_sequences" in recommendations
        assert any("Complex Automation Workflow" in seq for seq in recommendations["workflow_sequences"])
        
        # Should provide best practices for complex automations
        assert "best_practices" in recommendations
        assert any("Break complex automations" in practice for practice in recommendations["best_practices"])
        
        # Should suggest testing and monitoring
        assert "next_steps" in recommendations
        assert any("Test automation" in step for step in recommendations["next_steps"])
    
    def test_dashboard_performance_workflow_recommendations(self):
        """Test workflow recommendations for dashboard performance analysis."""
        recommendations = create_workflow_recommendations(
            "dashboards entities",
            {
                "total_entities": 75,
                "domain_breakdown": {"sensor": 40, "camera": 8, "light": 15, "switch": 12},
                "dashboard_url_path": "kitchen"
            }
        )
        
        # Should identify performance optimization opportunities
        assert "workflow_sequences" in recommendations
        assert any("Performance Optimization Workflow" in seq for seq in recommendations["workflow_sequences"])
        
        # Should suggest integration with other tools
        assert "integration_opportunities" in recommendations
        assert any("Sensor Integration" in opp for opp in recommendations["integration_opportunities"])
        
        # Should provide monitoring guidance
        assert "next_steps" in recommendations
        assert any("MCP tools" in step for step in recommendations["next_steps"])


class TestAdvancedIssueDetection:
    """Test advanced issue detection for Claude decision-making."""
    
    def test_automation_antipattern_detection(self):
        """Test detection of automation antipatterns."""
        automation_data = {
            "trigger": [
                {"platform": "state", "entity_id": "sensor.motion1"},
                {"platform": "state", "entity_id": "sensor.motion2"},
                {"platform": "state", "entity_id": "sensor.motion3"},
                {"platform": "state", "entity_id": "sensor.motion4"},
            ],
            "condition": [],  # No conditions with multiple triggers
            "action": [{"service": "light.turn_on"}]
        }
        
        metadata = {"automation_id": "test_automation"}
        issues = detect_advanced_issues("automations read", automation_data, metadata)
        
        # Should detect multiple triggers without conditions
        assert any("Multiple triggers without conditions" in issue for issue in issues)
    
    def test_very_long_action_sequence_detection(self):
        """Test detection of overly long action sequences."""
        automation_data = {
            "trigger": [{"platform": "state", "entity_id": "sensor.test"}],
            "condition": [],
            "action": [{"service": f"light.turn_on", "entity_id": f"light.{i}"} for i in range(20)]
        }
        
        metadata = {"automation_id": "test_automation"}
        issues = detect_advanced_issues("automations read", automation_data, metadata)
        
        # Should detect very long action sequences
        assert any("Very long action sequence" in issue for issue in issues)
    
    def test_problematic_trigger_detection(self):
        """Test detection of problematic trigger configurations."""
        automation_data = {
            "trigger": [
                {"platform": "time", "at": "12:00:00"},  # Time trigger without conditions
                {"platform": "state", "entity_id": "sensor.test"}  # State trigger without 'to'
            ],
            "condition": [],
            "action": [{"service": "light.turn_on"}]
        }
        
        metadata = {"automation_id": "test_automation"}
        issues = detect_advanced_issues("automations read", automation_data, metadata)
        
        # Should detect time trigger without conditions
        assert any("Time trigger without conditions" in issue for issue in issues)
        # Should detect state trigger without 'to' value
        assert any("State trigger without 'to' value" in issue for issue in issues)
    
    def test_dashboard_performance_issue_detection(self):
        """Test detection of dashboard performance issues."""
        metadata = {
            "total_entities": 80,
            "domain_breakdown": {"camera": 6, "media_player": 8, "sensor": 50}
        }
        
        issues = detect_advanced_issues("dashboards entities", [], metadata)
        
        # Should detect multiple cameras
        assert any("Multiple cameras on dashboard" in issue for issue in issues)
        # Should detect many media players
        assert any("Many media players" in issue for issue in issues)
    
    def test_response_time_issue_detection(self):
        """Test detection of performance issues based on response time."""
        metadata = {"response_time_ms": 6000}
        
        issues = detect_advanced_issues("automations list", [], metadata)
        
        # Should detect slow response time
        assert any("Slow response time" in issue for issue in issues)
    
    def test_health_based_issue_detection(self):
        """Test detection of issues based on Home Assistant health."""
        metadata = {"response_time_ms": 100}
        health_info = {
            "status": "error",
            "components": 20,
            "entities": 2000
        }
        
        issues = detect_advanced_issues("automations list", [], metadata, health_info)
        
        # Should detect health check failure
        assert any("health check failed" in issue for issue in issues)
        # Should detect high entity-to-component ratio (2000/20 = 100, which is > 50)
        assert any("High entity-to-component ratio" in issue for issue in issues)


class TestComplexityAnalysis:
    """Test automation complexity analysis for Claude optimization."""
    
    def test_simple_automation_analysis(self):
        """Test analysis of simple automation."""
        automation_data = {
            "trigger": [{"platform": "state", "entity_id": "sensor.motion"}],
            "condition": [],
            "action": [{"service": "light.turn_on", "entity_id": "light.living_room"}]
        }
        
        analysis = analyze_automation_complexity(automation_data)
        
        assert analysis["level"] == "simple"
        assert analysis["score"] <= 5
        assert len(analysis["optimizations"]) == 0
    
    def test_complex_automation_analysis(self):
        """Test analysis of complex automation."""
        automation_data = {
            "trigger": [
                {"platform": "state", "entity_id": "sensor.motion1"},
                {"platform": "state", "entity_id": "sensor.motion2"},
                {"platform": "time", "at": "sunset"},
                {"platform": "numeric_state", "entity_id": "sensor.lux"}
            ],
            "condition": [
                {"condition": "state", "entity_id": "person.user", "state": "home"},
                {"condition": "numeric_state", "entity_id": "sensor.temperature", "above": 20},
                {"condition": "time", "after": "18:00:00"}
            ],
            "action": [
                {"service": "light.turn_on", "entity_id": "light.living_room"},
                {"service": "light.turn_on", "entity_id": "light.kitchen"},
                {"service": "media_player.play_media", "entity_id": "media_player.speakers"},
                {"service": "climate.set_temperature", "entity_id": "climate.living_room"}
            ]
        }
        
        analysis = analyze_automation_complexity(automation_data)
        
        assert analysis["level"] in ["complex", "very_complex"]
        assert analysis["score"] > 15
        assert len(analysis["optimizations"]) > 0
        assert any("splitting into multiple automations" in opt for opt in analysis["optimizations"])
    
    def test_very_complex_automation_analysis(self):
        """Test analysis of very complex automation."""
        automation_data = {
            "trigger": [{"platform": "state", "entity_id": f"sensor.motion{i}"} for i in range(6)],
            "condition": [{"condition": "state", "entity_id": f"binary_sensor.door{i}", "state": "off"} for i in range(5)],
            "action": [{"service": "light.turn_on", "entity_id": f"light.room{i}"} for i in range(12)]
        }
        
        analysis = analyze_automation_complexity(automation_data)
        
        assert analysis["level"] == "very_complex"
        assert analysis["score"] > 25
        assert "Multiple triggers" in " ".join(analysis["factors"])
        assert "Complex conditions" in " ".join(analysis["factors"])
        assert "Many actions" in " ".join(analysis["factors"])


class TestDashboardPerformanceAnalysis:
    """Test dashboard performance analysis for optimization guidance."""
    
    def test_high_performance_dashboard(self):
        """Test analysis of well-optimized dashboard."""
        analysis = analyze_dashboard_performance(
            entity_count=25,
            domain_breakdown={"light": 10, "switch": 8, "sensor": 5, "binary_sensor": 2}
        )
        
        assert analysis["performance_score"] == 100
        assert len(analysis["issues"]) == 0
        assert len(analysis["optimizations"]) == 0
    
    def test_entity_heavy_dashboard(self):
        """Test analysis of dashboard with many entities."""
        analysis = analyze_dashboard_performance(
            entity_count=120,
            domain_breakdown={"sensor": 60, "light": 30, "switch": 20, "camera": 10}
        )
        
        assert analysis["performance_score"] < 100
        assert any("Very high entity count" in issue for issue in analysis["issues"])
        assert any("splitting dashboard" in opt for opt in analysis["optimizations"])
    
    def test_camera_heavy_dashboard(self):
        """Test analysis of dashboard with many cameras."""
        analysis = analyze_dashboard_performance(
            entity_count=30,
            domain_breakdown={"camera": 8, "light": 12, "sensor": 10}
        )
        
        assert analysis["performance_score"] < 100
        assert any("Multiple cameras" in issue for issue in analysis["issues"])
        assert any("camera thumbnails" in opt for opt in analysis["optimizations"])
    
    def test_sensor_heavy_dashboard(self):
        """Test analysis of dashboard with many sensors."""
        analysis = analyze_dashboard_performance(
            entity_count=60,
            domain_breakdown={"sensor": 45, "light": 10, "switch": 5}
        )
        
        assert analysis["performance_score"] < 100
        assert any("Many sensors" in issue for issue in analysis["issues"])
        assert any("sensor grouping" in opt for opt in analysis["optimizations"])


class TestPorcelainResponseQuality:
    """Test the quality and completeness of porcelain responses."""
    
    def test_porcelain_response_structure(self):
        """Test that porcelain responses have consistent structure."""
        formatter = PorcelainFormatter("test command")
        
        response_json = formatter.success(
            data={"test": "data"},
            metadata={"count": 1},
            suggestions={"common_actions": ["test action"]}
        )
        
        response = json.loads(response_json)
        
        # Verify required fields
        assert "command" in response
        assert "timestamp" in response
        assert "status" in response
        assert "metadata" in response
        assert "data" in response
        assert "suggestions" in response
        
        # Verify status
        assert response["status"] == "success"
        
        # Verify metadata includes response time
        assert "response_time_ms" in response["metadata"]
        assert isinstance(response["metadata"]["response_time_ms"], int)
    
    def test_porcelain_error_response_structure(self):
        """Test that porcelain error responses have consistent structure."""
        formatter = PorcelainFormatter("test command")
        
        response_json = formatter.error(
            error="Test error",
            error_code="TEST_001",
            suggestions={"troubleshooting": ["Check configuration"]}
        )
        
        response = json.loads(response_json)
        
        # Verify required fields for errors
        assert "command" in response
        assert "timestamp" in response
        assert "status" in response
        assert "error" in response
        assert "suggestions" in response
        
        # Verify status
        assert response["status"] == "error"
        
        # Verify error structure
        assert "type" in response["error"]
        assert "message" in response["error"]
        assert "code" in response["error"]
    
    def test_claude_optimization_completeness(self):
        """Test that responses include all elements needed for Claude optimization."""
        from ha_cli.common.porcelain import create_automation_suggestions, create_workflow_recommendations
        
        formatter = PorcelainFormatter("automations list")
        
        # Simulate rich automation data
        metadata = {
            "total_count": 15,
            "storage_breakdown": {"ui": 3, "file": 12},
            "home_assistant": {
                "url": "http://test:8123",
                "version": "2024.1.0",
                "health": {"status": "healthy", "entities": 500}
            }
        }
        
        # Use actual suggestion creation functions
        suggestions = create_automation_suggestions(15, {"ui": 3, "file": 12})
        workflow_recommendations = create_workflow_recommendations(
            "automations list",
            {"total_count": 15, "storage_breakdown": {"ui": 3, "file": 12}}
        )
        suggestions.update(workflow_recommendations)
        
        response_json = formatter.success(
            data=[{"id": "test", "alias": "Test Automation"}],
            metadata=metadata,
            suggestions=suggestions
        )
        
        response = json.loads(response_json)
        
        # Verify Claude-specific enhancements
        assert "workflow_sequences" in response["suggestions"]
        assert "best_practices" in response["suggestions"]
        assert "integration_opportunities" in response["suggestions"]
        
        # Verify metadata richness
        assert "home_assistant" in response["metadata"]
        assert "storage_breakdown" in response["metadata"]
        
        # Verify actionable suggestions
        suggestions_text = json.dumps(response["suggestions"])
        assert "ha-cli" in suggestions_text  # Should contain specific commands
        assert len(response["suggestions"]["common_actions"]) > 0


class TestIntegrationScenarios:
    """Test end-to-end integration scenarios that Claude might encounter."""
    
    def test_automation_discovery_workflow(self):
        """Test workflow for discovering and analyzing automations."""
        from ha_cli.common.porcelain import create_automation_suggestions, create_workflow_recommendations
        
        # Step 1: List automations
        list_formatter = PorcelainFormatter("automations list")
        list_metadata = {
            "total_count": 50,
            "storage_breakdown": {"ui": 10, "file": 40}
        }
        
        # Create realistic suggestions using actual functions
        suggestions = create_automation_suggestions(50, {"ui": 10, "file": 40})
        workflow_recommendations = create_workflow_recommendations(
            "automations list",
            {"total_count": 50, "storage_breakdown": {"ui": 10, "file": 40}}
        )
        suggestions.update(workflow_recommendations)
        
        list_response = json.loads(list_formatter.success(
            data=[{"id": f"auto_{i}", "alias": f"Automation {i}"} for i in range(50)],
            metadata=list_metadata,
            suggestions=suggestions
        ))
        
        # Should suggest next steps for automation analysis
        assert any("automations read" in action for action in list_response["suggestions"]["common_actions"])
        
        # Step 2: Read specific automation
        read_formatter = PorcelainFormatter("automations read")
        automation_data = {
            "id": "complex_lighting",
            "trigger": [{"platform": "state"} for _ in range(4)],
            "condition": [{"condition": "state"} for _ in range(3)],
            "action": [{"service": "light.turn_on"} for _ in range(6)]
        }
        
        read_metadata = {
            "automation_id": "complex_lighting",
            "complexity": {"level": "complex", "score": 20}
        }
        
        # Create proper workflow recommendations for automation read
        read_workflow_recommendations = create_workflow_recommendations(
            "automations read",
            {
                "automation_id": "complex_lighting",
                "complexity": {"level": "complex", "score": 20},
                "entity_dependencies": {"total_entities": 5, "by_domain": {"light": 3, "sensor": 2}}
            }
        )
        
        read_response = json.loads(read_formatter.success(
            data=automation_data,
            metadata=read_metadata,
            suggestions=read_workflow_recommendations
        ))
        
        # Should provide optimization guidance for complex automation
        assert "workflow_sequences" in read_response["suggestions"]
        assert any("Complex Automation Workflow" in seq for seq in read_response["suggestions"]["workflow_sequences"])
    
    def test_dashboard_optimization_workflow(self):
        """Test workflow for dashboard performance optimization."""
        from ha_cli.common.porcelain import create_dashboard_suggestions, create_workflow_recommendations
        
        # Step 1: List dashboards
        list_formatter = PorcelainFormatter("dashboards list")
        
        # Create realistic suggestions using actual functions
        suggestions = create_dashboard_suggestions(8)
        workflow_recommendations = create_workflow_recommendations(
            "dashboards list",
            {"total_count": 8}
        )
        suggestions.update(workflow_recommendations)
        
        list_response = json.loads(list_formatter.success(
            data=[{"id": "kitchen", "title": "Kitchen Dashboard"}],
            metadata={"total_count": 8},
            suggestions=suggestions
        ))
        
        # Should suggest entity analysis
        assert any("dashboards entities" in action for action in list_response["suggestions"]["common_actions"])
        
        # Step 2: Analyze dashboard entities
        entities_formatter = PorcelainFormatter("dashboards entities")
        entities_metadata = {
            "total_entities": 85,
            "domain_breakdown": {"sensor": 50, "camera": 8, "light": 15, "switch": 12},
            "performance": {
                "performance_score": 45,
                "issues": ["Very high entity count", "Multiple cameras impact bandwidth"],
                "optimizations": ["Consider splitting dashboard", "Use camera thumbnails"]
            }
        }
        
        # Create proper workflow recommendations for dashboard entities
        entities_workflow_recommendations = create_workflow_recommendations(
            "dashboards entities",
            {
                "total_entities": 85,
                "domain_breakdown": {"sensor": 50, "camera": 8, "light": 15, "switch": 12},
                "dashboard_url_path": "kitchen"
            }
        )
        
        entities_response = json.loads(entities_formatter.success(
            data=[{"entity_id": f"sensor.test_{i}", "domain": "sensor"} for i in range(85)],
            metadata=entities_metadata,
            suggestions=entities_workflow_recommendations
        ))
        
        # Should provide performance optimization guidance
        assert "workflow_sequences" in entities_response["suggestions"]
        assert any("Performance Optimization Workflow" in seq for seq in entities_response["suggestions"]["workflow_sequences"])
    
    def test_error_recovery_workflow(self):
        """Test error handling and recovery guidance."""
        formatter = PorcelainFormatter("automations read")
        
        error_response = json.loads(formatter.error(
            error="Automation 'nonexistent' not found",
            error_code="NOT_FOUND",
            suggestions={
                "troubleshooting": [
                    "Verify automation ID exists",
                    "Use 'ha-cli automations list --porcelain' to see all automations"
                ]
            }
        ))
        
        # Should provide specific troubleshooting steps
        assert "troubleshooting" in error_response["suggestions"]
        assert any("automations list" in step for step in error_response["suggestions"]["troubleshooting"])
        
        # Should maintain consistent error structure
        assert error_response["status"] == "error"
        assert "NOT_FOUND" in error_response["error"]["code"]