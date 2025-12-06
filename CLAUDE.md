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
│   ├── cli_utils.py          # Shared CLI utilities (setup_logging, run_async_command)
│   ├── client.py             # WebSocket/REST client with connection constants
│   ├── config.py             # Configuration management with security checks
│   ├── exceptions.py         # Custom exceptions with docstrings
│   ├── porcelain.py          # Structured JSON output for automation
│   └── utils.py              # General utilities (YAML, config file ops)
├── domains/                   # Domain-specific code
│   ├── automations/          # Automation management
│   ├── audit/                # Tech debt auditing (dead entities, unused automations, etc.)
│   ├── dashboards/           # Dashboard management
│   └── entities/             # Entity management
└── __main__.py               # CLI entry point
```

### Key Constants

WebSocket connection constants are defined in `ha_cli/common/client.py`:
- `WS_RECONNECT_BACKOFF = [1, 2, 4]` - Seconds between reconnection attempts
- `WS_HEARTBEAT_INTERVAL = 30` - Seconds between heartbeat pings
- `WS_PING_TIMEOUT = 10` - Seconds to wait for pong response
- `WS_MAX_MESSAGE_SIZE = 10MB` - Maximum WebSocket message size

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