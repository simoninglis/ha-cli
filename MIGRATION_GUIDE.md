# Migration Guide: ha-automation-cli to ha-cli

This guide helps you migrate from `ha-automation-cli` to the new multi-domain `ha-cli`.

## What's New

The tool has been transformed from a single-purpose automation CLI to a multi-domain tool that supports:
- **Automations** - All existing functionality preserved
- **Dashboards** - New functionality for managing Lovelace dashboards
- **More domains coming** - Extensible architecture for future additions

## Backward Compatibility

The `ha-automation` command continues to work exactly as before. All your existing scripts and workflows will continue to function without modification.

## Installation

### Using pip (Recommended)

```bash
# From PyPI (when published)
pip install ha-cli

# Or from GitHub
pip install git+https://github.com/singlis/ha-cli.git
```

### Using Poetry (Development)

```bash
git clone https://github.com/singlis/ha-cli.git
cd ha-cli
poetry install
```

### Command Entry Points

After installation, you have two entry points:

1. **New multi-domain CLI**: `ha-cli`
2. **Legacy automation CLI**: `ha-automation` (backward compatibility)

## Command Mapping

### Automation Commands

All automation commands now live under the `automations` subcommand:

| Old Command | New Command |
|-------------|-------------|
| `ha-automation list` | `ha-cli automations list` |
| `ha-automation create file.yaml` | `ha-cli automations create file.yaml` |
| `ha-automation read <id>` | `ha-cli automations read <id>` |
| `ha-automation update <id> file.yaml` | `ha-cli automations update <id> file.yaml` |
| `ha-automation delete <id>` | `ha-cli automations delete <id>` |
| `ha-automation enable <id>` | `ha-cli automations enable <id>` |
| `ha-automation disable <id>` | `ha-cli automations disable <id>` |
| `ha-automation reload` | `ha-cli automations reload` |
| `ha-automation monitor` | `ha-cli automations monitor` |
| `ha-automation version` | `ha-cli automations version` |

### New Dashboard Commands

The new CLI adds comprehensive dashboard management:

```bash
# List all dashboards
ha-cli dashboards list

# Read dashboard configuration
ha-cli dashboards read [url-path]

# Backup and restore dashboards
ha-cli dashboards backup [url-path]
ha-cli dashboards restore backup.yaml

# Create and delete dashboards
ha-cli dashboards create <id> <url-path> <title>
ha-cli dashboards delete <id>

# List entities in a dashboard
ha-cli dashboards entities [url-path]
```

## Configuration

Configuration remains the same. The tool uses the same:
- Environment variables: `HA_URL`, `HA_TOKEN`
- Config file: `~/.config/home-assistant-cli/config.json`
- Command-line options: `--url`, `--token`

## Python API Changes

If you're using the Python API directly:

### Old Import
```python
from ha_automation.client import HAClient
from ha_automation.service import AutomationCRUD
```

### New Import
```python
# For backward compatibility, old imports still work
from ha_automation.client import HAClient

# New structure
from ha_cli.common.client import HAClient
from ha_cli.domains.automations.service import AutomationCRUD
from ha_cli.domains.dashboards.service import DashboardService
```

## Benefits of Upgrading

1. **Unified Tool**: Manage multiple Home Assistant subsystems with one tool
2. **Dashboard Support**: Backup, restore, and manage Lovelace dashboards
3. **Entity Management**: Extract and analyze entity usage across dashboards
4. **Future Ready**: Extensible architecture for additional domains

## Troubleshooting

### Command Not Found

If `ha-cli` is not found, ensure you're using Poetry:
```bash
poetry run ha-cli --help
```

### Import Errors

If you get import errors with existing scripts, you can:
1. Continue using `ha-automation` command (recommended)
2. Update imports to use the new structure
3. Install with pip in editable mode: `pip install -e .`

### Version Check

Verify you have the latest version:
```bash
ha-cli version
# or
ha-automation version
```

Both should show version 0.3.0 or higher.

## Questions or Issues?

Please report any migration issues to the project repository.