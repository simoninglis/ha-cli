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

# List automations (if REST API available)
poetry run ha-cli automations list

# List dashboards
poetry run ha-cli dashboards list

# Extract entities from a dashboard
poetry run ha-cli dashboards entities mobile
```

## Available Commands

### Automation Commands
```bash
poetry run ha-cli automations list              # List all automations
poetry run ha-cli automations read <id>         # Show automation details
poetry run ha-cli automations create <file>     # Create from YAML file
poetry run ha-cli automations update <id> <file> # Update automation
poetry run ha-cli automations delete <id>       # Delete automation
poetry run ha-cli automations enable <id>       # Enable automation
poetry run ha-cli automations disable <id>      # Disable automation
poetry run ha-cli automations reload            # Reload all automations
poetry run ha-cli automations monitor           # Monitor automation events
```

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

# Create new automation from file
poetry run ha-cli automations create my-automation.yaml

# Migrate automation between storage types
poetry run ha-cli automations migrate motion_sensor_lights ui
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

### 404 Error on Automation Commands
If you get "Resource not found: /api/config/automation/config":
- The REST API requires the `config` integration to be enabled
- The tool will automatically fall back to WebSocket mode (with limited info)
- Force WebSocket mode with: `poetry run ha-cli automations list --websocket`
- Note: WebSocket mode only provides basic info (ID, name, state, last triggered)

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