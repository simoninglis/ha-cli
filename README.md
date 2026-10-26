# ha-cli (formerly ha-automation-cli)

Multi-domain command-line tool for managing Home Assistant configurations including automations, dashboards, and more.

## Latest Updates (v0.3.3)

- **Never hangs, never stores a token**: without a terminal, a missing URL or token is an immediate error (exit 1) instead of a prompt that waits forever; tokens are taken only from the environment (a token in `.env` or the config file is ignored with a warning) and never written to disk
- **Token login for screenshots and smoke tests**: the browser uses `HA_TOKEN`, so no HA password is needed; it cannot be navigated off the HA origin, and a rejected login is an error rather than a screenshot of the login page
- **HACS**: `hacs list`, `hacs audit` (HACS records vs dashboard resources) and a verified `hacs remove`
- **Idempotent integration setup**: `integrations setup --data/--data-file --if-missing`, failing unless the entry loads
- **Porcelain fix**: `entities` JSON output is no longer wrapped or markup-parsed (long values produced invalid JSON)
- **Config subentries**: Start, inspect, submit, and cancel newer integration subentry flows
- **Integration config flows**: Inspect and submit pending forms, including multi-step and options flows, using JSON input
- **🚀 Porcelain Mode**: New `--porcelain` flag provides structured JSON output optimized for Claude Code and automation tools
- **🧠 Intelligent Analysis**: Automatic complexity analysis, entity dependency mapping, and performance optimization suggestions
- **🔍 Advanced Issue Detection**: Proactive identification of automation antipatterns and configuration problems
- **📊 Rich Metadata**: Enhanced output with Home Assistant health info, performance metrics, and actionable suggestions
- **Automatic WebSocket Fallback**: When REST API is unavailable (`config` integration not enabled), automatically falls back to WebSocket for listing automations
- **Force WebSocket Mode**: Use `--websocket` flag to force WebSocket mode for automation listing
- **Improved Error Handling**: Better detection and handling of missing REST API endpoints

## Features

### Core Automation Management
- **List** all automations with their status
- **Create** new automations from YAML/JSON files
- **Read** automation details
- **Update** existing automations
- **Delete** automations with confirmation
- **Enable/Disable** automations via WebSocket
- **Reload** all automations
- **Dry-run mode** to preview changes before applying

### Dual Storage Support (NEW!)
- **Auto-detect** UI-style vs file-based automations
- **Create** automations in specific storage (UI or file)
- **Migrate** automations between storage types
- **Filter** listings by storage type
- **Preserve** format and structure during operations

### Real-Time WebSocket Features (NEW!)
- **Monitor** automation states and executions in real-time
- **Test triggers** interactively with live feedback
- **Stream events** from Home Assistant with filtering
- **Control** multiple automations simultaneously
- **Track execution metrics** and performance data
- **Auto-reconnection** for reliable WebSocket connections

### Dashboard Management
- **List** all dashboards with their properties
- **Read** dashboard configurations (storage or YAML mode)
- **Backup** dashboards to YAML/JSON files
- **Restore** dashboards from backup files
- **Create/Delete** new dashboards
- **Extract entities** referenced in dashboards
- **Update entity references** for bulk renaming

### Integration Configuration Flows
- **Inspect** pending config-flow forms and their schemas
- **Submit** arbitrary JSON form data to multi-step config flows
- **Inspect and update** integration options without editing `.storage`
- **Load form data from files** to avoid shell quoting and support repeatable operations

```bash
ha-cli integrations flow-show <flow-id> --json
ha-cli integrations flow-submit <flow-id> --data-file form.json
ha-cli integrations subentry-start <entry-id-or-domain> <subentry-type> --json
ha-cli integrations flow-submit <flow-id> --subentry --data-file form.json
ha-cli integrations options-show <entry-id-or-domain> --json
ha-cli integrations options-update <entry-id-or-domain> --data-file options.json
```

Use `--options` or `--subentry` with `flow-show`, `flow-submit`, and
`flow-cancel` for the corresponding flow type. Submitted data is not included
in command output, which avoids echoing secrets into logs.

### HACS
- **List** what HACS records as installed, with pending updates
- **Audit** HACS's records against the dashboard resources: cards HACS has lost
  track of (no update notices; removing one deletes a card in use), `/hacsfiles`
  resources no repository owns, installed cards nothing loads
- **Remove** a repository: shows what will be deleted, confirms, then verifies it's gone

```bash
ha-cli hacs list --updates
ha-cli hacs audit --porcelain
ha-cli hacs remove custom-cards/bom-radar-card
```

`integrations setup` also takes form fields for any integration, idempotently, and
exits non-zero unless the entry actually loads:

```bash
ha-cli integrations setup local_file --if-missing "Radar" \
  --data '{"name": "Radar", "file_path": "/config/radar.gif"}'
ha-cli integrations setup <domain> --data-file form.json   # secrets: argv is visible in ps
```

### Tech Debt Audit (NEW!)
- **dead-entities** - Find unavailable/unknown entities with integration grouping
- **duplicates** - Find duplicate entities with _2, _3, _4 suffixes
- **broken-automations** - Find automations referencing non-existent entities
- **fragile-automations** - Find automations referencing unavailable entities
- **unused-automations** - Find automations not triggered in N days
- **trigger-stats** - Show automation trigger statistics (most/least triggered)
- **integrations** - Show per-integration health summary
- **all** - Run all audit checks with combined summary

### Claude Code Integration (NEW!)
- **Porcelain Mode**: Structured JSON output with `--porcelain` flag
- **Intelligent Analysis**: Automation complexity scoring and entity dependency mapping
- **Smart Suggestions**: Context-aware workflow recommendations and next steps
- **Performance Metrics**: Dashboard analysis with optimization recommendations
- **Issue Detection**: Automatic identification of antipatterns and problems
- **Rich Metadata**: Home Assistant health, version info, and response times

### Developer Experience
- Cross-platform support (Linux, macOS, Windows)
- Async/await architecture for performance
- Rich terminal output with colors and tables
- Comprehensive error handling and recovery
- Extensive test coverage (1,100+ tests)

## Installation

### Using pipx (Recommended)

```bash
# Install from GitHub (public)
pipx install git+https://github.com/simoninglis/ha-cli.git

# Or install from Gitea (internal)
pipx install git+https://prod-vm-gitea.internal.kellgari.com.au/singlis/ha-cli.git

# Run commands directly
ha-cli --help
ha-automation --help  # Backward compatibility alias
```

### Using pip

```bash
# Install into a virtual environment (recommended)
python3.11 -m venv ~/.venvs/ha-cli
source ~/.venvs/ha-cli/bin/activate
pip install git+https://github.com/simoninglis/ha-cli.git

# Run commands
ha-cli --help
```

### Development Installation

```bash
git clone https://github.com/simoninglis/ha-cli.git
cd ha-cli
poetry install
poetry run ha-cli --help
```

## Understanding Automation Storage

Home Assistant supports two types of automation storage:

### File-Based Automations (`automations.yaml`)
- Traditional YAML-based automations
- Can have custom IDs or no IDs
- Uses singular format: `trigger`, `condition`, `action`
- Directly editable in YAML files
- Version control friendly

### UI-Style Automations (`.storage/automations`)
- Created/edited via Home Assistant UI
- Must have 32-character hexadecimal IDs
- Uses plural format: `triggers`, `conditions`, `actions`
- Stored in JSON format in `.storage` directory
- Not meant for direct editing

The CLI tool automatically detects which type an automation is and handles it appropriately. You can also explicitly specify the storage type when creating or migrating automations.

## Configuration

The tool can be configured in multiple ways (in order of precedence):

1. **Command-line arguments** - `--url`, and `--token NAME` (an env var's name)
2. **Environment variables**
3. **Configuration file** - `~/.config/home-assistant-cli/config.json` (URL only)
4. **Interactive prompt** - only at a terminal; elsewhere a missing value is an immediate error

**The token is only ever taken from the environment.** A token in `.env` or in the
config file is ignored with a warning, and ha-cli never writes one to disk.

### Environment Variables

**Required:**
- `HA_URL` or `HOME_ASSISTANT_URL` - Home Assistant URL (e.g., `http://homeassistant.local:8123`)
- `HA_TOKEN` or `HOME_ASSISTANT_TOKEN` - Long-lived access token (environment only)

**Optional (for SSH-based commands like `system logs`):**
- `HA_SSH_HOST` - SSH host for log/config commands (default: `homeassistant`)
- `HA_SSH_USER` - SSH user (default: `root`)

**Optional (for entity analysis links):**
- `HA_FILE_EDITOR_URL` - File Editor addon URL for direct file links in analysis output

**Optional (for dashboard screenshots and smoke tests):** the browser logs in with
`HA_TOKEN`; without one it uses the HA login form:
- `HA_USERNAME` - Home Assistant local username
- `HA_PASSWORD` - Home Assistant local password

Non-secret variables can be set in a `.env` file.

### Configuration File

Create `~/.config/home-assistant-cli/config.json`:

```json
{
  "url": "http://homeassistant.local:8123"
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
- `--token/-t` - **Name** of the environment variable holding the token (default `HA_TOKEN`). A literal token is refused: the command line is visible to every user on the host via `ps`
- `--timeout` - Request timeout in seconds (default: 10)
- `--json` - JSON output (where applicable)
- `--porcelain` - Structured output optimized for automation tools (NEW!)
- `--debug` - Enable debug logging

### Commands

#### List Automations

```bash
# List all automations in a table
ha-automation list

# Output as JSON
ha-automation list --json

# Output in porcelain format (structured for automation tools)
ha-automation list --porcelain

# Filter by storage type
ha-automation list --storage ui      # Only UI-style automations
ha-automation list --storage file    # Only file-based automations
ha-automation list --storage all     # All automations (default)

# With custom URL/token
ha-automation list --url http://ha.local:8123 --token HA_TOKEN   # the variable's NAME, never the token
```

#### Create Automation

```bash
# Create from YAML file (auto-detects storage type)
ha-automation create my-automation.yaml

# Create in specific storage
ha-automation create my-automation.yaml --storage ui    # Create as UI automation
ha-automation create my-automation.yaml --storage file  # Create as file automation

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

# Output in porcelain format with complexity analysis
ha-automation read automation_id --porcelain

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

#### Migrate Automation Storage

```bash
# Migrate from file-based to UI storage
ha-automation migrate my_automation ui

# Migrate from UI to file-based storage
ha-automation migrate abc123def456 file

# Skip confirmation prompt
ha-automation migrate my_automation ui --force

# Preview migration (dry-run)
ha-automation migrate my_automation ui --dry-run
```

#### Show Version

```bash
ha-automation version
```

### Dashboard Commands (NEW!)

The new multi-domain CLI provides comprehensive dashboard management:

#### List Dashboards

```bash
# List all dashboards
ha-cli dashboards list

# Output as JSON
ha-cli dashboards list --json

# Output in porcelain format with metadata
ha-cli dashboards list --porcelain
```

#### Read Dashboard Configuration

```bash
# Read default dashboard
ha-cli dashboards read

# Read specific dashboard by URL path
ha-cli dashboards read mobile

# Save to file
ha-cli dashboards read mobile --output mobile-dashboard.yaml

# Output as JSON
ha-cli dashboards read --format json
```

#### Backup and Restore Dashboards

```bash
# Backup dashboard to file (auto-generated filename)
ha-cli dashboards backup

# Backup specific dashboard with custom filename
ha-cli dashboards backup mobile --output mobile-backup.yaml

# Restore dashboard from backup
ha-cli dashboards restore mobile-backup.yaml

# Restore to a different dashboard
ha-cli dashboards restore mobile-backup.yaml --url-path tablet

# Validate backup file without restoring
ha-cli dashboards restore mobile-backup.yaml --validate-only
```

#### Create and Delete Dashboards

```bash
# Create new dashboard
ha-cli dashboards create tablet-dash tablet "Tablet Dashboard"

# Create with icon and options
ha-cli dashboards create admin-dash admin "Admin Panel" \
  --icon mdi:shield \
  --require-admin \
  --no-sidebar

# Delete dashboard
ha-cli dashboards delete tablet-dash

# Delete without confirmation
ha-cli dashboards delete tablet-dash --force
```

#### Entity Management

```bash
# List all entities referenced in a dashboard
ha-cli dashboards entities

# List entities in specific dashboard
ha-cli dashboards entities mobile

# Output as JSON for processing
ha-cli dashboards entities --json > dashboard-entities.json

# Output in porcelain format with performance analysis
ha-cli dashboards entities mobile --porcelain
```

### Porcelain Mode (Claude Code Integration)

Porcelain mode provides structured JSON output optimized for automation tools and Claude Code integration. It includes rich metadata, intelligent analysis, and actionable suggestions.

#### Key Features

- **Consistent Format**: Standardized JSON envelope across all commands
- **Rich Metadata**: Home Assistant health, version info, performance metrics
- **Smart Analysis**: Automation complexity scoring, entity dependency mapping
- **Issue Detection**: Automatic identification of problems and antipatterns
- **Actionable Suggestions**: Context-aware next steps and workflow recommendations

#### Example Output

```json
{
  "command": "automations read",
  "timestamp": "2025-06-14T08:27:15.822406+00:00",
  "status": "success",
  "metadata": {
    "automation_id": "goodnight_routine",
    "configuration_size": {
      "triggers": 2,
      "conditions": 1,
      "actions": 5
    },
    "complexity": {
      "score": 18,
      "level": "moderate",
      "factors": ["Multiple triggers (2)", "Complex conditions (1)"],
      "optimizations": ["Consider splitting into smaller automations"]
    },
    "entity_dependencies": {
      "total_entities": 8,
      "by_domain": {"light": 4, "sensor": 2, "switch": 2},
      "by_section": {"triggers": 2, "conditions": 1, "actions": 5}
    },
    "home_assistant": {
      "url": "http://homeassistant.local:8123",
      "connection_method": "rest",
      "health": {"status": "healthy", "entities": 423, "components": 47}
    },
    "response_time_ms": 42
  },
  "suggestions": {
    "common_actions": [
      "Test automation: Trigger manually in Home Assistant",
      "Check related entities: Use MCP tools to verify entity states"
    ],
    "workflow_sequences": [
      "Complex Automation Workflow: read → analyze → document → test → optimize"
    ],
    "best_practices": [
      "Break complex automations into smaller, testable parts",
      "Use meaningful variable names and add comments"
    ],
    "integration_opportunities": [
      "Entity Renaming: Use ha-rename tool for consistent entity naming"
    ]
  }
}
```

#### Usage Examples

```bash
# Get automation insights for Claude Code
ha-cli automations list --porcelain | jq '.suggestions.common_actions[]'

# Analyze dashboard performance
ha-cli dashboards entities kitchen --porcelain | jq '.metadata.performance'

# Find automation issues
ha-cli automations read complex_auto --porcelain | jq '.suggestions.detected_issues[]'

# Get workflow recommendations
ha-cli automations list --porcelain | jq '.suggestions.workflow_sequences[]'
```

### Audit Commands (Tech Debt Detection)

The audit subcommand helps identify and address tech debt in Home Assistant instances.

#### Dead Entities

Find entities that are unavailable or in unknown state:

```bash
# Find all dead entities
ha-cli audit dead-entities

# Output in porcelain format
ha-cli audit dead-entities --porcelain
```

#### Duplicate Entities

Find entities with _2, _3, _4 suffixes (typically from re-adding integrations):

```bash
# Find duplicate entities
ha-cli audit duplicates

# Porcelain output for processing
ha-cli audit duplicates --porcelain
```

#### Broken Automations

Find automations that reference non-existent entities:

```bash
# Find broken automations
ha-cli audit broken-automations
```

#### Fragile Automations

Find automations that reference unavailable (but existing) entities:

```bash
# Find fragile automations
ha-cli audit fragile-automations
```

#### Unused Automations

Find automations that have never been triggered or not triggered recently:

```bash
# Find automations never triggered (default)
ha-cli audit unused-automations

# Find automations not triggered in 90 days
ha-cli audit unused-automations --days 90
```

#### Trigger Statistics

Show automation trigger statistics - most and least triggered:

```bash
# Show trigger stats (top 20 by default)
ha-cli audit trigger-stats

# Show more results
ha-cli audit trigger-stats --limit 50
```

#### Integration Health

Show per-integration health summary with availability percentages:

```bash
# Show integration health
ha-cli audit integrations

# Porcelain output with detailed breakdown
ha-cli audit integrations --porcelain
```

#### Run All Audits

Run all audit checks and produce a combined summary:

```bash
# Run all audits
ha-cli audit all

# Output in porcelain format for automation
ha-cli audit all --porcelain
```

#### Exit Codes

Audit commands use meaningful exit codes:
- `0` - No issues found
- `1` - Issues found (warnings or errors)
- `2` - Command execution error

### WebSocket Real-Time Commands (Automations)

#### Monitor Automations

Monitor automation states and executions in real-time:

```bash
# Show current status of all automations
ha-automation monitor

# Follow mode - continuous monitoring with live updates
ha-automation monitor --follow

# See execution details with debug
ha-automation monitor --follow --debug
```

#### Test Triggers

Test automation triggers interactively:

```bash
# Test a trigger from a YAML file
ha-automation test-trigger trigger.yaml

# Interactive mode - see events as they happen
ha-automation test-trigger trigger.yaml --interactive

# Set custom timeout and max events
ha-automation test-trigger trigger.yaml --timeout 120 --max-events 5
```

Example trigger file:
```yaml
platform: state
entity_id: sensor.temperature
from: "20"
to: "25"
```

#### Stream Events

Stream Home Assistant events in real-time:

```bash
# Stream all events
ha-automation events

# Stream specific event type
ha-automation events state_changed

# Stream only automation-related events
ha-automation events --automations-only

# Show event details with debug
ha-automation events --debug
```

#### Control Automations

Control multiple automations via WebSocket:

```bash
# Enable multiple automations
ha-automation control enable automation1,automation2,automation3

# Disable automations (can omit 'automation.' prefix)
ha-automation control disable test1,test2

# Trigger automations manually
ha-automation control trigger my_automation

# Toggle automation states
ha-automation control toggle bedroom_lights,kitchen_lights
```

## Examples

### Using Environment Variables

```bash
export HA_URL="http://homeassistant.local:8123"
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