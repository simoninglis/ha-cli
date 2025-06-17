# WebSocket-based Automation Listing

This document describes the WebSocket-based approach for listing Home Assistant automations, which works around the REST API endpoint returning 404.

## Overview

Since the REST API endpoint `/api/config/automation/config` returns 404, we use the WebSocket connection to retrieve automation information by:

1. Connecting to Home Assistant's WebSocket API
2. Calling `get_states` to retrieve all entity states
3. Filtering for entities that start with `automation.`
4. Extracting automation details from the state attributes

## Implementation

### Test Script: `test_list_automations.py`

A simple script that demonstrates listing all automations with their basic information:
- ID and friendly name
- Enabled/disabled state
- Mode (single, restart, etc.)
- Last triggered time
- Currently running instances

### Enhanced Script: `list_automations_ws.py`

A production-ready script with advanced features:

#### Features
- **Filtering Options**:
  - `--state on/off` - Filter by enabled/disabled state
  - `--filter TEXT` - Search by name or ID (case insensitive)
  - `--triggered` - Show only automations that have been triggered
  - `--never-triggered` - Show only automations that have never been triggered
  - `--running` - Show only currently running automations

- **Output Formats**:
  - `--format table` - Tabular output (default)
  - `--format json` - JSON output for programmatic use
  - `--format simple` - Just automation IDs, one per line
  - `--format detailed` - Full details for each automation

- **Sorting Options**:
  - `--sort id/name/state/last_triggered` - Sort by field
  - `--reverse` - Reverse sort order

#### Usage Examples

```bash
# List all automations in table format
poetry run python list_automations_ws.py

# Show only disabled automations
poetry run python list_automations_ws.py --state off

# Search for vacuum-related automations
poetry run python list_automations_ws.py --filter vacuum

# Show automations that have never been triggered
poetry run python list_automations_ws.py --never-triggered

# Export all automations as JSON
poetry run python list_automations_ws.py --format json > automations.json

# List automation IDs sorted by last triggered time
poetry run python list_automations_ws.py --sort last_triggered --format simple
```

## Technical Details

### WebSocket Connection
- Uses the `HAClient` class from `ha_cli.common.client`
- Establishes WebSocket connection to `ws://HOST:PORT/api/websocket`
- Authenticates using long-lived access token
- Handles reconnection and heartbeat automatically

### Data Structure
Each automation state includes:
- `entity_id`: Full entity ID (e.g., `automation.vacuum_schedule`)
- `state`: "on" (enabled) or "off" (disabled)
- `attributes`:
  - `friendly_name`: Human-readable name
  - `last_triggered`: ISO timestamp or null
  - `mode`: Execution mode (single, restart, queued, parallel)
  - `current`: Number of currently running instances
  - `max`: Maximum allowed instances

### Configuration
The scripts read Home Assistant connection details from the `.mcp.json` file in the project root:
- URL from `mcpServers.home-assistant.env.HOME_ASSISTANT_URL`
- Token from `mcpServers.home-assistant.args` (extracts Bearer token)

## Integration with ha-cli

This WebSocket approach can be integrated into the main `ha-cli` tool as a fallback when the REST API is unavailable. The `get_automation_states()` method is already available in the `HAClient` class and provides the necessary functionality.

## Advantages

1. **Works with current HA setup** - No configuration changes needed
2. **Real-time data** - Gets current state directly from HA
3. **Rich information** - Includes runtime state (enabled/disabled, running instances)
4. **Efficient** - Single WebSocket call retrieves all automations

## Limitations

1. **No automation configuration** - Only state information, not the actual automation YAML
2. **Requires WebSocket** - More complex than simple REST calls
3. **Entity-based** - Relies on automation entities being properly registered