# ha-cli Tool Usage Guide

This guide is for USING the ha-cli tool to manage Home Assistant configurations. For developing/modifying the tool itself, see `../CLAUDE.md`.

## Tool Purpose
Command-line interface for managing Home Assistant automations, dashboards, and other configurations. Use this tool alongside MCP for comprehensive Home Assistant control.

## Architecture
- Home Assistant instance: 10.0.20.35:8123
- MCP Server: Pre-configured on Home Assistant
- Transport: SSE (Server-Sent Events)
- Authentication: Long-Lived Access Token
- Primary Interface: Claude Code with MCP tools

## Getting Credentials

The ha-cli tool now supports automatic loading from `.env` files!

### Option 1: Use .env file (Recommended)
1. A `.env` file has been created with credentials from `.mcp.json`
2. The tool will automatically load these values - no export needed!
3. See `ENV_SETUP.md` for details

### Option 2: Manual setup
1. **Find the Home Assistant URL and Token**: Check the `.mcp.json` file in the project root
2. The URL is in `env.HOME_ASSISTANT_URL` 
3. The token is in the `args` array after "Bearer"
4. Use these values to set environment variables:
   ```bash
   export HA_URL="<url from .mcp.json>"
   export HA_TOKEN="<token from .mcp.json>"
   ```

## Installation & Running

This tool uses Poetry. Always run commands with Poetry:

```bash
# Run the CLI
poetry run ha-cli --help
poetry run ha-automation --help  # backward compatibility

# Or use the convenience wrapper
./ha-cli --help
```

## Quick Start

```bash
# Set credentials from .mcp.json
export HA_URL="http://10.0.20.35:8123"
export HA_TOKEN="<token from .mcp.json>"

# List automations (via WebSocket)
poetry run ha-cli automations list

# List dashboards
poetry run ha-cli dashboards list

# Extract entities from a dashboard
poetry run ha-cli dashboards entities mobile
```

## Available Commands

### Automation Commands
```bash
poetry run ha-cli automations list              # List all automations (WebSocket)
poetry run ha-cli automations read <id>         # Show automation details (WebSocket)
poetry run ha-cli automations enable <id>       # Enable automation
poetry run ha-cli automations disable <id>      # Disable automation
poetry run ha-cli automations reload            # Reload all automations
poetry run ha-cli automations monitor           # Monitor automation events
```

**Note**: Create/update/delete operations are not available via the API.
Use the Home Assistant UI or edit `automations.yaml` directly.

### Dashboard Commands
```bash
poetry run ha-cli dashboards list               # List all dashboards
poetry run ha-cli dashboards read [url-path]    # Export dashboard config
poetry run ha-cli dashboards backup [url-path]  # Backup dashboard
poetry run ha-cli dashboards restore <file>     # Restore from backup
poetry run ha-cli dashboards entities [url-path] # Extract entity references
poetry run ha-cli dashboards create <id> <url> <title> # Create new dashboard
poetry run ha-cli dashboards delete <id>        # Delete dashboard
poetry run ha-cli dashboards screenshot <name>  # Capture dashboard screenshot
```

### Audit Commands (Tech Debt Detection)
```bash
poetry run ha-cli audit dead-entities           # Find unavailable/unknown entities
poetry run ha-cli audit duplicates              # Find _2, _3, _4 suffix duplicates
poetry run ha-cli audit broken-automations      # Automations with non-existent entity refs
poetry run ha-cli audit fragile-automations     # Automations with unavailable entity refs
poetry run ha-cli audit unused-automations      # Never triggered automations
poetry run ha-cli audit unused-automations --days 90  # Not triggered in 90 days
poetry run ha-cli audit trigger-stats           # Most/least triggered automations
poetry run ha-cli audit integrations            # Per-integration health summary
poetry run ha-cli audit all                     # Run all checks with combined summary
```

### deCONZ Commands (ZHA Migration)
```bash
poetry run ha-cli deconz list lights            # List deCONZ lights
poetry run ha-cli deconz list sensors           # List deCONZ sensors
poetry run ha-cli deconz list groups            # List deCONZ groups
poetry run ha-cli deconz list all               # List all deCONZ devices
poetry run ha-cli deconz search <query>         # Search devices by name
poetry run ha-cli deconz delete light <id>      # Delete light (with confirmation)
poetry run ha-cli deconz delete sensor <id> -f  # Delete sensor (skip confirmation)
```

**deCONZ Migration Workflow:**
1. `ha-cli deconz search "device name"` - Find device IEEE address and ID
2. `ha-cli deconz delete light|sensor <id>` - Remove from deCONZ
3. Factory reset device (varies by manufacturer)
4. Enable ZHA pairing in Home Assistant
5. Rename new ZHA entity to match naming conventions

### Labels Commands (Semantic Grouping)
```bash
poetry run ha-cli labels list                   # List all labels
poetry run ha-cli labels create <name>          # Create new label
poetry run ha-cli labels create <name> --icon mdi:lightbulb-group --color orange
poetry run ha-cli labels delete <label_id>      # Delete label (with confirmation)
poetry run ha-cli labels delete <label_id> -f   # Delete label (skip confirmation)
poetry run ha-cli labels assign <entity_id> <label_id>  # Add label to entity
poetry run ha-cli labels remove <entity_id> <label_id>  # Remove label from entity
poetry run ha-cli labels entities <label_id>    # List entities with label
```

**Label Workflow (per ADR-0006):**
1. `ha-cli labels create routine_kitchen_remote --icon mdi:lightbulb-group --color orange`
2. `ha-cli labels assign light.kitchen_ceiling routine_kitchen_remote`
3. Use in automations: `target: { label_id: routine_kitchen_remote }`

### Entity Commands
```bash
poetry run ha-cli entities list                   # List all entities
poetry run ha-cli entities list --domain light    # List entities by domain
poetry run ha-cli entities state <entity_id>      # Get entity state
poetry run ha-cli entities analyze <entity_id>    # Analyze entity impact
poetry run ha-cli entities update <entity_id> --name "New Name"  # Update friendly name
poetry run ha-cli entities update <entity_id> --icon mdi:lamp    # Set custom icon
poetry run ha-cli entities update <entity_id> --area living_room # Assign to area
poetry run ha-cli entities update <entity_id> --clear-icon       # Clear custom icon
poetry run ha-cli entities update <entity_id> --clear-area       # Remove from area
poetry run ha-cli entities update <entity_id> --dry-run --name "Preview"  # Preview changes
poetry run ha-cli entities update-batch updates.csv --dry-run    # Batch update from CSV
poetry run ha-cli entities update-batch updates.csv              # Execute batch update
poetry run ha-cli entities delete --entity-id sensor.orphaned    # Delete entity
poetry run ha-cli entities rename --search "old" --replace "new" # Rename entities
```

**Entity Update CSV Format:**
```csv
entity_id,name,icon,area_id
light.kitchen,Kitchen LEDs,mdi:led-strip,kitchen
sensor.temp,Temperature,mdi:thermometer,
switch.pump,,CLEAR,garage
```
- Empty cells = no change
- `CLEAR` = clear the value (remove icon, unassign area)

### Cloud Commands (Nabu Casa)
```bash
poetry run ha-cli cloud status                  # Show cloud connection status
poetry run ha-cli cloud alexa entities          # List entities available to Alexa
poetry run ha-cli cloud alexa entities --exposed # Show only exposed entities
poetry run ha-cli cloud alexa sync              # Trigger Alexa device discovery

# Entity exposure management (Issue #68)
poetry run ha-cli cloud alexa expose <entity_id>       # Expose single entity to Alexa
poetry run ha-cli cloud alexa expose --from-file <yaml> # Expose entities from YAML file
poetry run ha-cli cloud alexa hide <entity_id>         # Hide single entity from Alexa
poetry run ha-cli cloud alexa hide --all-except <yaml> # Hide all except entities in file
poetry run ha-cli cloud alexa sync-filter --file <yaml> # Sync exposure with YAML file
poetry run ha-cli cloud alexa sync-filter --file <yaml> --dry-run # Preview changes
```

**Entity Exposure Management:**

Nabu Casa Alexa uses intersection logic - entities must be BOTH:
1. In the YAML filter (`integration_cloud.yaml` → `includes/voice_exposure_entities.yaml`)
2. Have `should_expose: true` in the entity registry

The `sync-filter` command is the "magic" command that syncs entity registry with YAML:
- Enables exposure for all entities IN the YAML file
- Disables exposure for all entities NOT in the YAML file

**Example workflow:**
```bash
# Preview changes
ha-cli cloud alexa sync-filter --file includes/voice_exposure_entities.yaml --dry-run

# Apply changes
ha-cli cloud alexa sync-filter --file includes/voice_exposure_entities.yaml

# Tell Alexa to rediscover
ha-cli cloud alexa sync
```

**Cloud Status Output:**
- Login state, email, subscription expiration
- Cloud connection status
- Remote UI state (domain shown if connected)
- Alexa/Google Assistant enabled/linked state
- Alexa entity count from filter

**Exit codes:**
- `0` = No issues found
- `1` = Issues found (warnings/errors)
- `2` = Command error

### Porcelain Mode (NEW!)
**All commands now support `--porcelain` for structured output optimized for Claude Code:**

```bash
# Automations with rich metadata
poetry run ha-cli automations list --porcelain
poetry run ha-cli automations read <id> --porcelain

# Dashboards with entity analysis  
poetry run ha-cli dashboards list --porcelain
poetry run ha-cli dashboards entities <url-path> --porcelain
```

**Porcelain Features:**
- **Rich Metadata**: Counts, performance metrics, Home Assistant info
- **Smart Suggestions**: Context-aware next actions and troubleshooting
- **Issue Detection**: Automatically identifies potential problems
- **Consistent Format**: Standardized JSON envelope across all commands
- **Error Handling**: Structured error responses with helpful guidance

### Common Options
- `--porcelain`: Output in structured format for automation (NEW!)
- `--json`: Output in JSON format
- `--yaml`: Output in YAML format (dashboards)
- `--url`: Override Home Assistant URL
- `--token`: Override access token
- `--help`: Show command help

## Usage Examples

### Working with Automations
```bash
# List all automations with their status
poetry run ha-cli automations list

# Filter by storage type
poetry run ha-cli automations list --storage ui     # UI-created only
poetry run ha-cli automations list --storage file   # File-based only

# Read full automation details
poetry run ha-cli automations read kitchen_motion_activated_light

# Enable/disable automations
poetry run ha-cli automations enable motion_sensor_lights
poetry run ha-cli automations disable motion_sensor_lights
```

### Working with Dashboards
```bash
# List all dashboards
poetry run ha-cli dashboards list

# Export dashboard configuration
poetry run ha-cli dashboards read mobile --yaml > mobile-dash.yaml

# Extract all entity references from a dashboard
poetry run ha-cli dashboards entities mobile --json

# Backup and restore
poetry run ha-cli dashboards backup mobile --output mobile-backup.yaml
poetry run ha-cli dashboards restore mobile-backup.yaml
```

## Troubleshooting

### Automation API Limitations
The tool uses WebSocket API exclusively for automations because the REST API
(`/api/config/automation/config`) is undocumented and requires the `config`
integration to be enabled (which most installations don't have).

**What works via WebSocket:**
- List automations (basic info: ID, name, mode, state, last triggered)
- Read automation details (full configuration)
- Enable/disable automations
- Reload automations

**What requires manual action:**
- Create/update/delete automations - use HA UI or edit `automations.yaml`

### Connection Issues
- Verify credentials match those in `.mcp.json`
- Check Home Assistant is accessible at the URL
- Ensure the access token hasn't expired

## Related Tools

### ha-rename - Entity Renaming Tool
A separate tool for bulk renaming Home Assistant entities:

```bash
# List all entities
poetry run ha-rename

# Search and replace with regex
poetry run ha-rename --search "^climate\.(.*)(?<!_ac)$" --replace "climate.\1_ac"

# Export entities to CSV
poetry run ha-rename --output-csv entities-backup.csv
```

See ha-rename documentation for full usage.

## Notes for Claude

### When to Use This Tool vs MCP
- **Use ha-cli for**: Bulk operations, backups, entity extraction, file-based management
- **Use MCP tools for**: Real-time control, individual device commands, state queries
- **Combine both for**: Complete Home Assistant management workflows

### Important Context
- This tool is part of a larger entity renaming project
- Always check credentials in `.mcp.json` first
- REST API may not be available for automations - use workarounds
- For tool development, see `../CLAUDE.md`

## Technical Documentation

### Code Architecture

The ha-cli codebase follows a domain-driven structure with shared utilities:

```
ha_cli/
├── common/                    # Shared infrastructure
│   ├── cli_utils.py          # Shared CLI utilities (setup_logging, run_async_command, write_output)
│   ├── client.py             # WebSocket/REST client with connection constants
│   ├── config.py             # Configuration management with security checks
│   ├── exceptions.py         # Custom exceptions with docstrings
│   ├── porcelain.py          # Structured JSON output for automation
│   └── utils.py              # General utilities (YAML, config file ops)
├── domains/                   # Domain-specific code
│   ├── automations/          # Automation management
│   │   ├── commands/         # Command modules (modular architecture)
│   │   │   ├── list_cmd.py   # List automations
│   │   │   ├── read_cmd.py   # Read automation details
│   │   │   ├── control_cmd.py # Enable/disable/reload
│   │   │   └── crud_cmd.py   # Create/update/delete
│   │   ├── cli.py            # Command registration
│   │   ├── models.py         # Pydantic models
│   │   └── service.py        # Business logic
│   ├── areas/                # Area management (with CRUD operations)
│   ├── audit/                # Tech debt auditing (dead entities, unused automations, etc.)
│   ├── dashboards/           # Dashboard management
│   ├── deconz/               # deCONZ device management (ZHA migration)
│   │   ├── cli.py            # List, search, delete commands
│   │   └── service.py        # SSH-based deCONZ API interactions
│   └── entities/             # Entity management
└── __main__.py               # CLI entry point
```

### Modular CLI Architecture

Large CLI modules are split into focused command modules under `commands/`:
- Each command module is <300 lines for maintainability
- Commands are imported and registered in the main `cli.py`
- Tests patch at the command module level (e.g., `ha_cli.domains.automations.commands.list_cmd.HAClient`)

### Key Constants

WebSocket connection constants are defined in `ha_cli/common/client.py`:
- `WS_RECONNECT_BACKOFF = [1, 2, 4]` - Seconds between reconnection attempts
- `WS_HEARTBEAT_INTERVAL = 30` - Seconds between heartbeat pings
- `WS_PING_TIMEOUT = 10` - Seconds to wait for pong response
- `WS_MAX_MESSAGE_SIZE = 10MB` - Maximum WebSocket message size

### SSH Safety Pattern

When implementing SSH-based commands (like deconz or system domains), use this pattern:

```python
# SSH connection options for safety
SSH_OPTIONS = [
    "-o", "BatchMode=yes",           # Never prompt for password
    "-o", "ConnectTimeout=10",       # Connection timeout
    "-o", "StrictHostKeyChecking=accept-new",
]
SSH_TIMEOUT = 30  # Command timeout in seconds

def _run_ssh(self, cmd: str, timeout: int = SSH_TIMEOUT) -> str:
    ssh_args = ["ssh", *SSH_OPTIONS, self.ssh_host, cmd]
    try:
        result = subprocess.run(ssh_args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SSHError(f"SSH command timed out after {timeout}s")

    if result.returncode == 255:  # SSH connection error
        raise SSHError(f"SSH connection error: {result.stderr.strip()}")
    return result.stdout
```

**Key points:**
- Always use `BatchMode=yes` to prevent interactive prompts
- Set both connection timeout (`ConnectTimeout`) and command timeout (`timeout=`)
- Check for return code 255 (SSH-specific connection errors)
- Create domain-specific exceptions (`SSHError`, `APIError`) for structured handling

### Security Features

Config files containing tokens are protected:
- **Permission checking**: Warns if config file readable by group/others
- **Auto-secure**: New config files created with mode 0600 (owner read/write only)
- **Actionable warnings**: Suggests `chmod 600` command when insecure

### Home Assistant Integration
For detailed technical information about Home Assistant API constraints, data quality issues, and integration patterns, see:
- [`docs/HOME_ASSISTANT_INTEGRATION.md`](docs/HOME_ASSISTANT_INTEGRATION.md) - Comprehensive guide on working with Home Assistant APIs

### Key Points for Quick Reference

#### Control Characters in Output
**Issue**: JSON output may appear corrupted with newlines in unexpected places
**Root Cause**: Python's `print()` function, not the data
**Solution**: Use `sys.stdout.write()` for all structured output:

```python
# Instead of: print(json.dumps(data, indent=2))
import sys
sys.stdout.write(json.dumps(data, indent=2))
sys.stdout.write('\n')
sys.stdout.flush()
```

#### API Availability
- REST API (`/api/config/automation/config`) requires `config` integration
- Always implement WebSocket fallbacks
- Set WebSocket `max_size=10*1024*1024` for large responses

#### Common Issues
- 404 on automation endpoints: REST API not available, use WebSocket
- Large payload errors: Increase WebSocket max_size
- Invalid JSON output: Use sys.stdout.write() instead of print()