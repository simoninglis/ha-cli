# ha-automation-cli

Command-line helper for managing Home Assistant automations over HTTP + WebSocket.

## Features

- **List** all automations with their status
- **Create** new automations from YAML/JSON files
- **Read** automation details
- **Update** existing automations
- **Delete** automations with confirmation
- **Enable/Disable** automations via WebSocket
- **Reload** all automations
- **Dry-run mode** to preview changes before applying
- Cross-platform support (Linux, macOS, Windows)
- Async/await architecture for performance
- Rich terminal output with colors and tables

## Installation

### Using Poetry (Recommended)

```bash
cd tools/ha-automation-cli
poetry install
poetry run ha-automation --help
```

### Using pip

```bash
cd tools/ha-automation-cli
pip install -e .
ha-automation --help
```

## Configuration

The tool can be configured in multiple ways (in order of precedence):

1. **Command-line arguments** - Highest priority
2. **Environment variables**
3. **Configuration file** - `~/.config/ha-automation/config.json`
4. **Interactive prompt** - If no config found

### Environment Variables

- `HA_URL` or `HOME_ASSISTANT_URL` - Home Assistant URL
- `HA_TOKEN` or `HOME_ASSISTANT_TOKEN` - Long-lived access token

### Configuration File

Create `~/.config/ha-automation/config.json`:

```json
{
  "url": "http://10.0.20.35:8123",
  "token": "your-long-lived-access-token"
}
```

### Generate Access Token

1. Go to your Home Assistant profile: http://your-ha-instance:8123/profile
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token"
4. Give it a name (e.g., "CLI Tool")
5. Copy the token - you won't see it again!

## Usage

### Global Options

All commands support these options:

- `--url/-u` - Home Assistant URL
- `--token/-t` - Access token or environment variable name
- `--timeout` - Request timeout in seconds (default: 10)
- `--json` - JSON output (where applicable)
- `--debug` - Enable debug logging

### Commands

#### List Automations

```bash
# List all automations in a table
ha-automation list

# Output as JSON
ha-automation list --json

# With custom URL/token
ha-automation list --url http://ha.local:8123 --token YOUR_TOKEN
```

#### Create Automation

```bash
# Create from YAML file
ha-automation create my-automation.yaml

# Create from JSON file
ha-automation create my-automation.json

# Preview what would be created (dry-run)
ha-automation create my-automation.yaml --dry-run
```

Example YAML file:

```yaml
alias: "Turn on lights at sunset"
trigger:
  - platform: sun
    event: sunset
action:
  - service: light.turn_on
    target:
      entity_id: light.living_room
mode: single
```

#### Read Automation Details

```bash
# Show automation details
ha-automation read automation_id

# Output as JSON
ha-automation read automation_id --json

# Show full YAML with debug
ha-automation read automation_id --debug
```

#### Update Automation

```bash
# Update from file
ha-automation update automation_id updated-config.yaml

# Preview what would be updated (dry-run)
ha-automation update automation_id updated-config.yaml --dry-run
```

#### Delete Automation

```bash
# Delete with confirmation prompt
ha-automation delete automation_id

# Delete without confirmation
ha-automation delete automation_id --force

# Preview what would be deleted (dry-run)
ha-automation delete automation_id --dry-run
```

#### Enable/Disable Automation

```bash
# Enable
ha-automation enable automation_id

# Disable
ha-automation disable automation_id
```

#### Reload All Automations

```bash
# Reload after manual config changes
ha-automation reload
```

#### Show Version

```bash
ha-automation version
```

## Examples

### Using Environment Variables

```bash
export HA_URL="http://10.0.20.35:8123"
export HA_TOKEN="your-token-here"

# Now you can use commands without --url/--token
ha-automation list
ha-automation enable sunrise_lights
```

### Using Token from Environment Variable

```bash
# Store token in env var
export MY_HA_TOKEN="eyJ0eXAiOiJKV1..."

# Reference the env var name (not the value)
ha-automation list --token MY_HA_TOKEN
```

### Dry-Run Mode

```bash
# Test creating an automation without actually creating it
ha-automation create sunset-lights.yaml --dry-run

# Preview updates before applying
ha-automation update my_automation updated-config.yaml --dry-run

# See what would be deleted
ha-automation delete old_automation --dry-run

# Combine with other options
ha-automation create complex-automation.yaml --dry-run --debug
```

### Batch Operations

```bash
# Disable all automations with "test" in the name
ha-automation list --json | jq -r '.[] | select(.alias | contains("test")) | .id' | \
  xargs -I {} ha-automation disable {}

# Export all automations to files
mkdir automations-backup
ha-automation list --json | jq -r '.[].id' | \
  while read id; do
    ha-automation read "$id" > "automations-backup/${id}.yaml"
  done
```

## Error Handling

The tool uses specific exit codes:

- `0` - Success
- `1` - Client usage error (bad arguments, file not found)
- `2` - HTTP/WebSocket error (network issues, timeouts)
- `3` - Home Assistant error (401, 404, 500, etc.)

## Development

### Running Tests

```bash
make test
```

### Code Quality

```bash
# Linting
make lint

# Type checking
make mypy

# Format code
make format

# Run all checks
make lint test
```

### Building

```bash
# Build wheel
make build

# Clean build artifacts
make clean
```

## Troubleshooting

### Connection Refused

- Verify Home Assistant is running and accessible
- Check the URL includes the port (e.g., `:8123`)
- Ensure you're on the same network or VPN

### 401 Unauthorized

- Check your access token is valid
- Ensure the token has necessary permissions
- Try generating a new token

### 404 Not Found

- For automations: Verify the automation ID exists
- For API endpoints: Ensure you have the latest HA version

### WebSocket Errors

- The tool will automatically retry WebSocket connections (max 3 attempts)
- Check Home Assistant logs for WebSocket errors
- Ensure your HA instance supports WebSocket API

### SSL/TLS Issues

If using HTTPS with self-signed certificates:

```bash
# Disable SSL verification (not recommended for production)
export HTTPX_VERIFY=false
```

## Requirements

- Python 3.11+
- Home Assistant instance with:
  - REST API enabled
  - WebSocket API enabled
  - Valid long-lived access token

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## Notes

- Creating, updating, and deleting automations requires Home Assistant 2023.x or newer
- Some operations may require additional Home Assistant integrations
- The tool respects Home Assistant's rate limiting