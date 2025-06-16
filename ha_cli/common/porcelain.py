"""Porcelain mode utilities for structured JSON output optimized for Claude Code."""

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict

from .exceptions import HAAutomationError


class CleanJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that removes control characters from strings."""
    
    def encode(self, obj):
        """Encode object with control character sanitization."""
        return super().encode(self._sanitize_recursive(obj))
    
    def _sanitize_recursive(self, obj):
        """Recursively sanitize all strings in an object."""
        if isinstance(obj, str):
            # Remove control characters (0x00-0x1F except tab, newline, carriage return)
            return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', obj)
        elif isinstance(obj, dict):
            return {k: self._sanitize_recursive(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_recursive(item) for item in obj]
        else:
            return obj


class PorcelainMetadata(BaseModel):
    """Metadata included in porcelain responses."""
    
    total_count: Optional[int] = None
    filtered_count: Optional[int] = None
    filters_applied: List[str] = []
    home_assistant: Optional[Dict[str, Any]] = None
    response_time_ms: Optional[int] = None
    
    model_config = ConfigDict(extra="allow")  # Allow additional metadata fields


class PorcelainSuggestions(BaseModel):
    """Suggestions for common actions and troubleshooting."""
    
    common_actions: List[str] = []
    detected_issues: List[str] = []
    related_commands: List[str] = []
    troubleshooting: List[str] = []
    
    model_config = ConfigDict(extra="allow")  # Allow additional suggestion fields


class PorcelainError(BaseModel):
    """Error information in porcelain format."""
    
    type: str
    message: str
    code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class PorcelainResponse(BaseModel):
    """Standard porcelain response envelope."""
    
    command: str
    timestamp: str
    status: str  # "success" or "error"
    metadata: Optional[PorcelainMetadata] = None
    data: Optional[Union[List[Any], Dict[str, Any], Any]] = None
    error: Optional[PorcelainError] = None
    suggestions: Optional[PorcelainSuggestions] = None


class PorcelainFormatter:
    """Utility class for creating porcelain-formatted responses."""
    
    def __init__(self, command: str):
        """Initialize formatter with command name."""
        self.command = command
        self.start_time = time.time()
    
    def success(
        self,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None,
        suggestions: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a success response in porcelain format."""
        response_time_ms = int((time.time() - self.start_time) * 1000)
        
        # Create metadata with response time
        porcelain_metadata = PorcelainMetadata(
            response_time_ms=response_time_ms,
            **(metadata or {})
        )
        
        # Create suggestions
        porcelain_suggestions = PorcelainSuggestions(**(suggestions or {}))
        
        response = PorcelainResponse(
            command=self.command,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="success",
            metadata=porcelain_metadata,
            data=data,
            suggestions=porcelain_suggestions
        )
        
        # Use custom JSON encoder to handle any control characters
        response_dict = response.model_dump(exclude_none=True)
        return json.dumps(response_dict, indent=2, cls=CleanJSONEncoder)
    
    def _sanitize_json_output(self, json_str: str) -> str:
        """Sanitize JSON output by removing control characters."""
        # Remove control characters (0x00-0x1F except tab, newline, carriage return)
        return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', json_str)
    
    def error(
        self,
        error: Union[Exception, HAAutomationError, str],
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        suggestions: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create an error response in porcelain format."""
        response_time_ms = int((time.time() - self.start_time) * 1000)
        
        # Extract error information
        if isinstance(error, HAAutomationError):
            error_type = error.__class__.__name__
            error_message = error.message
            error_details = error.details or {}
            if details:
                error_details.update(details)
        elif isinstance(error, Exception):
            error_type = error.__class__.__name__
            error_message = str(error)
            error_details = details or {}
        else:
            error_type = "Error"
            error_message = str(error)
            error_details = details or {}
        
        # Create error object
        porcelain_error = PorcelainError(
            type=error_type,
            message=error_message,
            code=error_code,
            details=error_details if error_details else None
        )
        
        # Add default troubleshooting suggestions based on error type
        default_suggestions = self._get_default_error_suggestions(error_type)
        if suggestions:
            default_suggestions.update(suggestions)
        
        porcelain_suggestions = PorcelainSuggestions(**default_suggestions)
        
        # Create metadata with response time
        porcelain_metadata = PorcelainMetadata(response_time_ms=response_time_ms)
        
        response = PorcelainResponse(
            command=self.command,
            timestamp=datetime.now(timezone.utc).isoformat(),
            status="error",
            metadata=porcelain_metadata,
            error=porcelain_error,
            suggestions=porcelain_suggestions
        )
        
        # Use custom JSON encoder to handle any control characters
        response_dict = response.model_dump(exclude_none=True)
        return json.dumps(response_dict, indent=2, cls=CleanJSONEncoder)
    
    def _get_default_error_suggestions(self, error_type: str) -> Dict[str, List[str]]:
        """Get default troubleshooting suggestions based on error type."""
        suggestions_map = {
            "AuthenticationError": {
                "troubleshooting": [
                    "Check token in .mcp.json file",
                    "Verify Home Assistant URL is accessible",
                    "Generate new long-lived access token in HA Profile → Security",
                    "Ensure token has not expired"
                ]
            },
            "ConnectionError": {
                "troubleshooting": [
                    "Check Home Assistant URL is correct and accessible",
                    "Verify Home Assistant is running",
                    "Check network connectivity",
                    "Verify firewall allows connections on port 8123"
                ]
            },
            "NotFoundError": {
                "troubleshooting": [
                    "Verify the requested resource exists",
                    "Check if REST API endpoint is available",
                    "Try using WebSocket mode with --websocket flag",
                    "Ensure Home Assistant config integration is enabled"
                ]
            },
            "TimeoutError": {
                "troubleshooting": [
                    "Increase timeout with --timeout flag",
                    "Check Home Assistant performance",
                    "Verify network latency",
                    "Try during lower system load"
                ]
            }
        }
        
        return suggestions_map.get(error_type, {
            "troubleshooting": [
                "Check Home Assistant logs for more details",
                "Verify ha-cli configuration is correct",
                "Try with --debug flag for more information"
            ]
        })


def create_automation_suggestions(automation_count: int, storage_breakdown: Dict[str, int]) -> Dict[str, List[str]]:
    """Create automation-specific suggestions based on current state."""
    suggestions = {
        "common_actions": [
            "View details: ha-cli automations read <id> --porcelain",
            "Enable/disable: ha-cli automations enable|disable <id>",
            "Monitor events: ha-cli automations monitor --porcelain"
        ],
        "related_commands": [
            "dashboards list --porcelain",
            "automations monitor --porcelain"
        ],
        "detected_issues": []
    }
    
    # Add context-specific suggestions
    if automation_count == 0:
        suggestions["detected_issues"].append("No automations found")
        suggestions["common_actions"] = [
            "Create automation: ha-cli automations create --file <yaml-file>",
            "Check Home Assistant configuration"
        ]
    elif automation_count > 100:
        suggestions["detected_issues"].append(f"Large number of automations ({automation_count}) may impact performance")
        suggestions["common_actions"].insert(0, "Consider reviewing and optimizing automations")
    
    # Storage-specific suggestions
    if storage_breakdown.get("file", 0) == 0 and storage_breakdown.get("ui", 0) > 0:
        suggestions["common_actions"].append("Consider migrating UI automations to YAML files for version control")
    
    return suggestions


def create_dashboard_suggestions(dashboard_count: int) -> Dict[str, List[str]]:
    """Create dashboard-specific suggestions based on current state."""
    suggestions = {
        "common_actions": [
            "View dashboard: ha-cli dashboards read <url-path> --porcelain",
            "Extract entities: ha-cli dashboards entities <url-path> --porcelain",
            "Backup dashboard: ha-cli dashboards backup <url-path>"
        ],
        "related_commands": [
            "automations list --porcelain",
            "dashboards entities --porcelain"
        ],
        "detected_issues": []
    }
    
    if dashboard_count == 0:
        suggestions["detected_issues"].append("No dashboards found")
        suggestions["common_actions"] = [
            "Create dashboard: ha-cli dashboards create <id> <url> <title>",
            "Check Home Assistant Lovelace configuration"
        ]
    
    return suggestions


async def get_home_assistant_health(client) -> Dict[str, Any]:
    """Get Home Assistant health and version information."""
    health_info = {
        "status": "unknown",
        "version": None,
        "components": 0,
        "entities": 0,
        "uptime": None,
        "database_size": None,
        "last_boot": None
    }
    
    try:
        # Try to get version and basic info
        config = await client.get("/api/config")
        if config:
            health_info.update({
                "version": config.get("version"),
                "components": len(config.get("components", [])),
                "latitude": config.get("latitude"),
                "longitude": config.get("longitude"),
                "elevation": config.get("elevation"),
                "time_zone": config.get("time_zone"),
                "currency": config.get("currency"),
                "country": config.get("country"),
                "language": config.get("language"),
                "status": "healthy"
            })
        
        # Try to get entity count
        try:
            states = await client.get("/api/states")
            if states:
                health_info["entities"] = len(states)
        except Exception:
            pass  # Entity count is optional
            
        # Try to get supervisor info (if available)
        try:
            supervisor = await client.get("/api/hassio/supervisor/info")
            if supervisor:
                health_info.update({
                    "supervisor_version": supervisor.get("data", {}).get("version"),
                    "healthy": supervisor.get("data", {}).get("healthy", True),
                    "supported": supervisor.get("data", {}).get("supported", True)
                })
        except Exception:
            pass  # Supervisor info is optional (not available in all installations)
            
    except Exception as e:
        health_info["status"] = "error"
        health_info["error"] = str(e)
    
    return health_info


def create_home_assistant_metadata(
    url: str,
    connection_method: str,
    version: Optional[str] = None,
    health_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create Home Assistant metadata for porcelain responses."""
    metadata = {
        "url": url,
        "connection_method": connection_method
    }
    
    if version:
        metadata["version"] = version
    elif health_info and health_info.get("version"):
        metadata["version"] = health_info["version"]
    
    if health_info:
        # Add health information
        metadata["health"] = {
            "status": health_info.get("status", "unknown"),
            "components": health_info.get("components", 0),
            "entities": health_info.get("entities", 0)
        }
        
        # Add system information if available
        if health_info.get("time_zone"):
            metadata["system"] = {
                "time_zone": health_info.get("time_zone"),
                "country": health_info.get("country"),
                "language": health_info.get("language")
            }
        
        # Add supervisor info if available
        if health_info.get("supervisor_version"):
            metadata["supervisor"] = {
                "version": health_info.get("supervisor_version"),
                "healthy": health_info.get("healthy", True),
                "supported": health_info.get("supported", True)
            }
    
    return metadata


def analyze_automation_complexity(automation_data: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze automation complexity and provide optimization insights."""
    complexity = {
        "score": 0,
        "level": "simple",
        "factors": [],
        "optimizations": []
    }
    
    trigger_count = len(automation_data.get("trigger", []))
    condition_count = len(automation_data.get("condition", []))
    action_count = len(automation_data.get("action", []))
    
    # Calculate complexity score
    score = 0
    score += min(trigger_count * 2, 10)  # Max 10 points for triggers
    score += min(condition_count * 3, 15)  # Max 15 points for conditions  
    score += min(action_count * 2, 10)  # Max 10 points for actions
    
    complexity["score"] = score
    
    # Determine complexity level
    if score <= 5:
        complexity["level"] = "simple"
    elif score <= 15:
        complexity["level"] = "moderate"
    elif score <= 25:
        complexity["level"] = "complex"
    else:
        complexity["level"] = "very_complex"
    
    # Add complexity factors
    if trigger_count > 3:
        complexity["factors"].append(f"Multiple triggers ({trigger_count})")
    if condition_count > 2:
        complexity["factors"].append(f"Complex conditions ({condition_count})")
    if action_count > 5:
        complexity["factors"].append(f"Many actions ({action_count})")
    
    # Add optimization suggestions
    if complexity["level"] in ["complex", "very_complex"]:
        complexity["optimizations"].append("Consider splitting into multiple automations")
        complexity["optimizations"].append("Review for redundant conditions")
    
    if trigger_count > 5:
        complexity["optimizations"].append("Consider consolidating similar triggers")
    
    if action_count > 8:
        complexity["optimizations"].append("Consider using scripts for action sequences")
    
    return complexity


def extract_entity_references(automation_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract and analyze entity references from automation configuration."""
    entities = {
        "referenced": [],
        "by_domain": {},
        "triggers": [],
        "conditions": [],
        "actions": []
    }
    
    def extract_from_dict(data, section):
        """Recursively extract entity IDs from configuration dict."""
        if isinstance(data, dict):
            for key, value in data.items():
                if key in ["entity_id", "entity_ids"]:
                    if isinstance(value, str):
                        entities["referenced"].append(value)
                        entities[section].append(value)
                    elif isinstance(value, list):
                        entities["referenced"].extend(value)
                        entities[section].extend(value)
                elif isinstance(value, (dict, list)):
                    extract_from_dict(value, section)
        elif isinstance(data, list):
            for item in data:
                extract_from_dict(item, section)
    
    # Extract from each section
    extract_from_dict(automation_data.get("trigger", []), "triggers")
    extract_from_dict(automation_data.get("condition", []), "conditions")
    extract_from_dict(automation_data.get("action", []), "actions")
    
    # Remove duplicates and analyze by domain
    entities["referenced"] = list(set(entities["referenced"]))
    
    for entity_id in entities["referenced"]:
        if "." in entity_id:
            domain = entity_id.split(".", 1)[0]
            if domain not in entities["by_domain"]:
                entities["by_domain"][domain] = []
            entities["by_domain"][domain].append(entity_id)
    
    return entities


def analyze_dashboard_performance(entity_count: int, domain_breakdown: Dict[str, int]) -> Dict[str, Any]:
    """Analyze dashboard performance characteristics."""
    analysis = {
        "performance_score": 100,
        "issues": [],
        "optimizations": [],
        "monitoring_needed": []
    }
    
    # Entity count impact
    if entity_count > 100:
        analysis["performance_score"] -= 30
        analysis["issues"].append(f"Very high entity count ({entity_count})")
        analysis["optimizations"].append("Consider splitting dashboard into multiple views")
    elif entity_count > 50:
        analysis["performance_score"] -= 15
        analysis["issues"].append(f"High entity count ({entity_count})")
        analysis["optimizations"].append("Monitor dashboard load times")
    
    # Domain-specific analysis
    sensor_count = domain_breakdown.get("sensor", 0)
    if sensor_count > 30:
        analysis["performance_score"] -= 10
        analysis["issues"].append(f"Many sensors ({sensor_count}) may cause frequent updates")
        analysis["optimizations"].append("Consider using sensor grouping or statistics")
    
    camera_count = domain_breakdown.get("camera", 0)
    if camera_count > 5:
        analysis["performance_score"] -= 20
        analysis["issues"].append(f"Multiple cameras ({camera_count}) impact bandwidth")
        analysis["optimizations"].append("Use camera thumbnails instead of live streams")
    
    # History-heavy entities
    history_entities = domain_breakdown.get("history_stats", 0) + domain_breakdown.get("recorder", 0)
    if history_entities > 10:
        analysis["performance_score"] -= 10
        analysis["monitoring_needed"].append("Monitor database size growth")
    
    # Final score adjustment
    analysis["performance_score"] = max(0, analysis["performance_score"])
    
    return analysis


def create_workflow_recommendations(
    command: str,
    data_context: Dict[str, Any],
    health_info: Optional[Dict[str, Any]] = None
) -> Dict[str, List[str]]:
    """Create intelligent workflow recommendations based on current context."""
    recommendations = {
        "next_steps": [],
        "workflow_sequences": [],
        "best_practices": [],
        "integration_opportunities": []
    }
    
    # Command-specific recommendations
    if command == "automations list":
        automation_count = data_context.get("total_count", 0)
        storage_breakdown = data_context.get("storage_breakdown", {})
        
        if automation_count > 0:
            recommendations["next_steps"].extend([
                "Review specific automation: ha-cli automations read <id> --porcelain",
                "Check automation performance: Look for complex automations with high trigger counts",
                "Monitor automation execution: ha-cli automations monitor --porcelain"
            ])
            
            # Storage-based recommendations
            if storage_breakdown.get("ui", 0) > 0:
                recommendations["workflow_sequences"].append(
                    "UI Automation Workflow: list → read → backup → migrate to file"
                )
            
            if storage_breakdown.get("file", 0) > 0:
                recommendations["workflow_sequences"].append(
                    "File Automation Workflow: list → read → validate → test → version control"
                )
            
            # Size-based recommendations
            if automation_count > 50:
                recommendations["best_practices"].extend([
                    "Consider organizing automations by functional area",
                    "Document complex automations with descriptions",
                    "Implement automation testing procedures"
                ])
    
    elif command == "automations read":
        automation_id = data_context.get("automation_id")
        if automation_id:
            recommendations["next_steps"].extend([
                f"Test automation: Trigger manually in Home Assistant",
                f"Check related entities: Use MCP tools to verify entity states",
                f"Monitor automation: ha-cli automations monitor --porcelain"
            ])
            
            # Complexity-based recommendations
            complexity = data_context.get("complexity", {})
            if complexity.get("level") in ["complex", "very_complex"]:
                recommendations["workflow_sequences"].append(
                    "Complex Automation Workflow: read → analyze → document → test → optimize"
                )
                recommendations["best_practices"].extend([
                    "Break complex automations into smaller, testable parts",
                    "Use meaningful variable names and add comments",
                    "Implement error handling for critical automations"
                ])
    
    elif command == "dashboards list":
        dashboard_count = data_context.get("total_count", 0)
        
        if dashboard_count > 0:
            recommendations["next_steps"].extend([
                "Analyze dashboard entities: ha-cli dashboards entities <url-path> --porcelain",
                "Review dashboard performance: Look for entity-heavy dashboards",
                "Backup important dashboards: ha-cli dashboards backup <url-path>"
            ])
            
            recommendations["workflow_sequences"].append(
                "Dashboard Analysis Workflow: list → entities → performance review → optimize"
            )
            
            if dashboard_count > 10:
                recommendations["best_practices"].extend([
                    "Organize dashboards by user or functional area",
                    "Use conditional cards to reduce entity load",
                    "Regular dashboard cleanup and optimization"
                ])
    
    elif command == "dashboards entities":
        entity_count = data_context.get("total_entities", 0)
        domain_breakdown = data_context.get("domain_breakdown", {})
        
        if entity_count > 0:
            recommendations["next_steps"].extend([
                "Check entity states: Use MCP tools for real-time status",
                "Find related automations: ha-cli automations list --porcelain",
                "Validate entity availability: Ensure all entities exist"
            ])
            
            # Performance-based recommendations
            if entity_count > 50:
                recommendations["workflow_sequences"].append(
                    "Performance Optimization Workflow: entities → analyze → group → optimize → test"
                )
            
            # Domain-specific recommendations
            if "sensor" in domain_breakdown:
                recommendations["integration_opportunities"].append(
                    "Sensor Integration: Consider sensor grouping, statistics, or filtering"
                )
            
            if "automation" in domain_breakdown:
                recommendations["integration_opportunities"].append(
                    "Automation Integration: Review automation complexity and dashboard impact"
                )
    
    # Health-based recommendations
    if health_info:
        entity_total = health_info.get("entities", 0)
        if entity_total > 1000:
            recommendations["best_practices"].extend([
                "Large installation detected - implement regular performance monitoring",
                "Consider database optimization and cleanup procedures",
                "Monitor system resources and automation execution times"
            ])
        
        if health_info.get("status") != "healthy":
            recommendations["next_steps"].insert(0, 
                "Address Home Assistant health issues before proceeding"
            )
    
    # Cross-cutting integration opportunities
    recommendations["integration_opportunities"].extend([
        "Entity Renaming: Use ha-rename tool for consistent entity naming",
        "Version Control: Track automation and dashboard changes in git",
        "Monitoring: Set up alerts for automation failures and performance issues"
    ])
    
    return recommendations


def detect_advanced_issues(
    command: str,
    data: Any,
    metadata: Dict[str, Any],
    health_info: Optional[Dict[str, Any]] = None
) -> List[str]:
    """Detect advanced configuration and performance issues."""
    issues = []
    
    # Response time issues
    response_time = metadata.get("response_time_ms", 0)
    if response_time > 5000:
        issues.append(f"Slow response time ({response_time}ms) - check Home Assistant performance")
    elif response_time > 2000:
        issues.append(f"Elevated response time ({response_time}ms) - monitor system load")
    
    # Health-based issues
    if health_info:
        status = health_info.get("status", "unknown")
        if status == "error":
            issues.append("Home Assistant health check failed - investigate system issues")
        elif status == "unknown":
            issues.append("Unable to determine Home Assistant health status")
        
        # Component/entity ratio analysis
        components = health_info.get("components", 0)
        entities = health_info.get("entities", 0)
        
        if components > 0 and entities > 0:
            ratio = entities / components
            if ratio > 50:
                issues.append(f"High entity-to-component ratio ({ratio:.1f}) - potential performance impact")
            elif ratio < 2:
                issues.append(f"Low entity-to-component ratio ({ratio:.1f}) - underutilized integrations")
    
    # Command-specific advanced issues
    if command == "automations list":
        automation_count = metadata.get("total_count", 0)
        storage_breakdown = metadata.get("storage_breakdown", {})
        
        # Mixed storage mode detection
        ui_count = storage_breakdown.get("ui", 0)
        file_count = storage_breakdown.get("file", 0)
        
        if ui_count > 0 and file_count > 0:
            if ui_count > file_count * 2:
                issues.append("Predominantly UI-based setup - consider migration to file-based for version control")
            elif file_count > ui_count * 2:
                issues.append("Predominantly file-based setup - ensure UI automations are properly documented")
        
        # Automation density analysis
        if automation_count > 100:
            issues.append("Very high automation count - consider organization and performance review")
    
    elif command == "automations read":
        if isinstance(data, dict):
            # Check for common automation antipatterns
            triggers = data.get("trigger", [])
            conditions = data.get("condition", [])
            actions = data.get("action", [])
            
            # Antipattern: No conditions with multiple triggers
            if len(triggers) > 3 and len(conditions) == 0:
                issues.append("Multiple triggers without conditions - may cause unintended executions")
            
            # Antipattern: Very long action sequences
            if len(actions) > 15:
                issues.append("Very long action sequence - consider using scripts or breaking into smaller automations")
            
            # Check for potentially problematic trigger types
            for trigger in triggers:
                if trigger.get("platform") == "time" and not conditions:
                    issues.append("Time trigger without conditions - ensure this is intentional")
                elif trigger.get("platform") == "state" and not trigger.get("to"):
                    issues.append("State trigger without 'to' value - may trigger on any state change")
    
    elif command == "dashboards entities":
        entity_count = metadata.get("total_entities", 0)
        domain_breakdown = metadata.get("domain_breakdown", {})
        
        # Resource-intensive entity detection
        if domain_breakdown.get("camera", 0) > 3:
            issues.append("Multiple cameras on dashboard - significant bandwidth and processing impact")
        
        if domain_breakdown.get("media_player", 0) > 5:
            issues.append("Many media players - check for inactive or duplicate entities")
        
        # Orphaned entity detection patterns
        if "automation" in domain_breakdown:
            issues.append("Dashboard references automations - ensure they're enabled and functional")
        
        # Performance scaling issues
        if entity_count > 0 and len(domain_breakdown) > 12:
            issues.append("High domain diversity - dashboard may be trying to do too much")
    
    return issues