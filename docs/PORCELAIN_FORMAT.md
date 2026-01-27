# Porcelain Mode Format Specification

This document describes the structured JSON output format used by ha-cli's `--porcelain` mode, optimized for programmatic consumption by Claude Code and other automation tools.

## Overview

Porcelain mode provides a consistent, machine-readable JSON format across all ha-cli commands with rich metadata, actionable suggestions, and comprehensive error handling.

## Standard Response Envelope

All porcelain responses follow this consistent structure:

```json
{
  "command": "string",                       // Command that was executed
  "timestamp": "ISO8601",                    // UTC timestamp when response was created
  "status": "success|partial_success|error", // Response status
  "metadata": { ... },                       // Command-specific metadata
  "data": [ ... ] | { ... },                // Response data (success/partial_success)
  "error": { ... },                          // Error information (error only)
  "suggestions": { ... }                     // Contextual suggestions and guidance
}
```

### Status Values
- `success`: All operations completed successfully
- `partial_success`: Some operations succeeded, some failed (includes both `data` and failure details)
- `error`: All operations failed or a fatal error occurred

## Success Response Format

### Required Fields
- `command`: The exact command executed (e.g., "automations list")
- `timestamp`: ISO 8601 UTC timestamp (e.g., "2025-06-14T08:27:15.822406+00:00")
- `status`: Always "success" for successful operations
- `metadata`: Object containing operation metadata
- `data`: Array or object containing the requested data
- `suggestions`: Object with actionable suggestions

### Metadata Structure
Metadata typically includes:
```json
{
  "response_time_ms": 74,       // Response time in milliseconds
  "home_assistant": {           // Home Assistant connection info (optional)
    "url": "http://homeassistant.local:8123",
    "connection_method": "rest|websocket"
  }
  // ... command-specific metadata
}
```
Note: `home_assistant` is included when the command connects to Home Assistant, but may be omitted for error responses or commands that don't require a connection.

### Suggestions Structure
```json
{
  "common_actions": [           // Frequently used follow-up actions
    "View details: ha-cli automations read <id> --porcelain"
  ],
  "detected_issues": [          // Automatically detected problems
    "Large number of entities (150) may impact performance"
  ],
  "related_commands": [         // Related commands that might be useful
    "ha-cli dashboards list --porcelain"
  ],
  "next_steps": [               // Suggested follow-up actions (context-specific)
    "ha-cli cloud alexa sync  # Tell Alexa to rediscover"
  ]
}
```
Note: Fields within `suggestions` are optional; commands include only relevant fields.

## Error Response Format

### Required Fields
- `command`: The command that failed
- `timestamp`: When the error occurred
- `status`: Always "error" for error responses  
- `metadata`: Minimal metadata (usually just response_time_ms)
- `error`: Detailed error information
- `suggestions`: Troubleshooting guidance

### Error Object Structure
```json
{
  "type": "AuthenticationError",  // Error class name
  "message": "Invalid token",     // Human-readable message
  "code": "AUTH_001",            // Optional error code
  "details": {                   // Optional additional details
    "endpoint": "/api/config/automation",
    "http_status": 401
  }
}
```

### Error Suggestions
Error responses include troubleshooting guidance:
```json
{
  "troubleshooting": [
    "Check token in .env file or environment variables",
    "Verify Home Assistant URL is accessible",
    "Generate new long-lived access token"
  ],
  "related_commands": [
    "Test connection: ha-cli system info --porcelain"
  ]
}
```

## Command-Specific Formats

### Automations List

**Metadata:**
```json
{
  "total_count": 51,
  "filtered_count": 51,
  "filters_applied": ["storage=file"],
  "storage_breakdown": {"ui": 0, "file": 51},
  "response_time_ms": 74,
  "home_assistant": { ... }
}
```

**Data Format:**
```json
[
  {
    "id": "send_canary_notification",
    "alias": "Notify of canary breach", 
    "mode": "single",
    "storage_type": "file",
    "last_triggered": "2025-06-14T08:00:00+00:00",
    "enabled": true,
    "entity_id": "automation.send_canary_notification"
  }
]
```

### Automations Read

**Metadata:**
```json
{
  "automation_id": "goodnight",
  "configuration_size": {
    "triggers": 2,
    "conditions": 1, 
    "actions": 5
  },
  "response_time_ms": 42,
  "home_assistant": { ... }
}
```

**Data Format:**
```json
{
  "id": "goodnight",
  "alias": "Goodnight",
  "description": "Turn off lights and set sleep mode",
  "mode": "single",
  "max": null,
  "enabled": true,
  "entity_id": "automation.goodnight",
  "trigger": [ ... ],      // Full trigger configuration
  "condition": [ ... ],    // Full condition configuration  
  "action": [ ... ],       // Full action configuration
  "variables": { ... },    // Automation variables
  "trace": { ... }         // Trace configuration
}
```

### Dashboards List

**Metadata:**
```json
{
  "total_count": 9,
  "storage_mode_breakdown": {"storage": 9, "yaml": 0},
  "sidebar_count": 9,
  "admin_only_count": 0,
  "response_time_ms": 19,
  "home_assistant": { ... }
}
```

**Data Format:**
```json
[
  {
    "id": "default",
    "url_path": "",
    "title": "Default",
    "mode": "storage",
    "show_in_sidebar": true,
    "require_admin": false,
    "icon": null
  }
]
```

### Dashboard Entities

**Metadata:**
```json
{
  "dashboard_url_path": "dashboard-office",
  "total_entities": 1,
  "unique_domains": 1,
  "domain_breakdown": {"weather": 1},
  "response_time_ms": 22,
  "home_assistant": { ... }
}
```

**Data Format:**
```json
[
  {
    "entity_id": "weather.holland_park",
    "domain": "weather", 
    "friendly_name": "Weather.Holland Park"
  }
]
```

## Issue Detection

Porcelain mode automatically detects and reports common issues:

### Automation Issues
- No triggers defined (automation will never execute)
- No actions defined (automation will do nothing)
- Mode requiring 'max' parameter without it being set
- Large number of automations (performance concern)

### Dashboard Issues  
- Mixed storage modes (storage vs yaml)
- Large number of entities (performance concern)
- Hidden dashboards not shown in sidebar
- Empty dashboards with no entities

### General Issues
- Authentication failures
- Connection timeouts
- Missing resources
- Validation errors

## Contextual Suggestions

### Smart Actions
Suggestions are context-aware and include:
- **Next logical steps**: Based on current command and results
- **Performance optimizations**: When issues are detected
- **Related operations**: Commands that work well together
- **Troubleshooting**: When errors occur

### Cross-Command Integration
Suggestions help navigate between related commands:
- From automations to dashboards that might reference them
- From dashboard entities to automation management
- From errors to diagnostic commands

## Integration with Claude Code

The porcelain format is optimized for Claude Code workflows:

### Rich Context
- Comprehensive metadata enables better decision-making
- Issue detection helps Claude proactively suggest fixes
- Performance metrics inform optimization recommendations

### Actionable Intelligence
- Specific command suggestions reduce follow-up queries
- Error troubleshooting guides enable self-service problem solving
- Related commands suggestions enable efficient workflows

### Consistency
- Standardized format across all commands
- Predictable error handling
- Uniform suggestion structure

## Example Workflows

### Complete Automation Analysis
```bash
# Get overview
ha-cli automations list --porcelain

# Investigate specific automation
ha-cli automations read automation_id --porcelain

# Check related dashboards
ha-cli dashboards entities dashboard-name --porcelain
```

### Dashboard Entity Review
```bash
# List all dashboards  
ha-cli dashboards list --porcelain

# Extract entities from each dashboard
ha-cli dashboards entities dashboard-office --porcelain
ha-cli dashboards entities dashboard-kitchen --porcelain

# Cross-reference with automations
ha-cli automations list --porcelain
```

## Best Practices

### For Tool Developers
1. Always check the `status` field first
2. Handle both success and error response formats
3. Use `suggestions` to guide next actions
4. Monitor `response_time_ms` for performance
5. Parse `detected_issues` for proactive problem solving

### For Claude Code Integration
1. Use rich metadata for decision-making
2. Present `detected_issues` to users as recommendations
3. Suggest `common_actions` as next steps
4. Use `related_commands` for workflow optimization
5. Parse error `troubleshooting` for self-service resolution

## Versioning

The porcelain format follows semantic versioning:
- **Major**: Breaking changes to envelope structure
- **Minor**: New optional fields or command-specific metadata
- **Patch**: Bug fixes, improved suggestions, additional issue detection

Current version: 1.0.0
