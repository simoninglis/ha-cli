# ha-cli: Multi-Domain Home Assistant Management Tool

## Feature: Transform ha-automation-cli to Multi-Domain ha-cli
**Status**: Mostly Complete  
**Started**: 2025-01-14  
**Updated**: 2025-01-15

## Summary of Current State

The transformation to ha-cli is **mostly complete**! All three domains have been implemented:

1. **Automations**: Basic operations (list, read) + porcelain mode
2. **Dashboards**: Full CRUD operations + entity extraction + porcelain mode
3. **Entities**: Complete suite including rename, analyze, import/export + porcelain mode

### What's Still Missing

Based on the original plan, these automation commands haven't been implemented yet:
- `create` - Create new automation from YAML file
- `update` - Update existing automation
- `delete` - Delete automation
- `enable/disable` - Enable/disable automation
- `reload` - Reload all automations
- `monitor` - Monitor automation events in real-time
- `migrate` - Migrate automation between storage types (UI ↔ file)

### Additional Features Implemented (Not in Original Plan)

1. **Porcelain Mode**: All commands support `--porcelain` for structured JSON output
2. **Entity Analysis**: Cross-domain usage analysis
3. **Bulk Operations**: CSV import/export for entity operations
4. **Dashboard Views**: List views within dashboards
5. **Comprehensive Error Handling**: With helpful suggestions  
**Priority**: High

## Background

Following the successful implementation of dual storage support for automations, we need to extend our tooling to handle entity renaming across all Home Assistant subsystems. The goal is to support migration to consistent naming conventions by updating entity references in dashboards, scripts, scenes, and other subsystems when entities are renamed.

Research shows that dashboards follow the same dual storage pattern as automations:
- **Storage mode**: JSON in `.storage/`, WebSocket API management
- **YAML mode**: Direct file editing

This architectural similarity makes it natural to extend our existing tool rather than create separate tools for each subsystem.

## Goals

1. **Unified Tool**: Single CLI for all Home Assistant management tasks
2. **Entity Migration**: Support bulk entity renaming across all subsystems
3. **Code Reuse**: Leverage existing WebSocket client and storage patterns
4. **Extensibility**: Easy to add new domains (scripts, scenes, etc.)
5. **Backward Compatibility**: Existing `ha-automation` commands continue working

## Architecture Overview

```
ha-cli
├── automations         # Existing automation management
│   ├── list
│   ├── create
│   ├── update
│   ├── delete
│   ├── monitor
│   └── migrate
│
├── dashboards          # New dashboard management
│   ├── list
│   ├── read
│   ├── backup
│   ├── restore
│   └── rename-entities
│
└── entities (future)   # Cross-domain entity operations
    ├── rename
    ├── find-usage
    └── validate
```

## Implementation Phases

### Phase 1: Refactor to Multi-Domain Architecture ✅
**Duration**: 1-2 days  
**Status**: Complete

#### 1.1 Project Restructure
- [x] Create new directory structure:
  ```
  ha_cli/
  ├── __init__.py
  ├── __main__.py
  ├── cli.py              # Root CLI definition
  ├── common/
  │   ├── __init__.py
  │   ├── client.py       # Move HAClient here
  │   ├── config.py       # Move config utilities here
  │   ├── exceptions.py   # Move exceptions here
  │   └── storage/        # Move storage patterns here
  ├── domains/
  │   ├── __init__.py
  │   ├── automations/    # Move automation code here
  │   └── dashboards/     # New dashboard code
  └── utils.py
  ```

#### 1.2 Update Project Metadata
- [x] Update `pyproject.toml`:
  - Change name to `ha-cli`
  - Add `ha-cli` script entry point
  - Keep `ha-automation` as compatibility alias
  - Update description and documentation

#### 1.3 Implement Root CLI
- [x] Create root `cli.py` with Typer subcommands
- [x] Add `automations` subcommand routing to existing code
- [x] Add `dashboards` subcommand (fully implemented)
- [x] Implement backward compatibility for `ha-automation`

#### 1.4 Move and Refactor Common Code
- [x] Extract shared client code to `common/client.py`
- [x] Move config management to common modules
- [x] Create base storage classes for automations
- [x] Update imports throughout codebase
- [x] Add porcelain mode support in `common/porcelain.py`

### Phase 2: Implement Dashboard Support ✅
**Duration**: 3-4 days  
**Status**: Complete

#### 2.1 Dashboard Models
- [x] Create `domains/dashboards/models.py`:
  ```python
  @dataclass
  class Card:
      type: str
      entity: Optional[str]
      entities: Optional[List[str]]
      # ... other card properties
  
  @dataclass
  class View:
      title: str
      path: Optional[str]
      cards: List[Card]
      # ... sections support
  
  @dataclass
  class Dashboard:
      title: Optional[str]
      views: List[View]
  ```

#### 2.2 WebSocket Integration
- [x] Add dashboard methods to HAClient:
  - [x] `list_dashboards()` - WebSocket `lovelace/dashboards`
  - [x] `get_dashboard_config(url_path=None)` - WebSocket `lovelace/config`
  - [x] `save_dashboard_config(config, url_path=None)` - WebSocket `lovelace/config/save`
  - [x] `delete_dashboard(url_path)` - WebSocket `lovelace/config/delete`

#### 2.3 Dashboard Storage Managers
- [x] **DashboardService**: Unified service handling all dashboard types
  - [x] Load via WebSocket
  - [x] Save via WebSocket
  - [x] Handle all dashboard operations
  - [x] Support both storage and YAML modes

#### 2.4 Dashboard CLI Commands
- [x] `ha-cli dashboards list` - List all dashboards
- [x] `ha-cli dashboards read <url_path>` - Show dashboard config
- [x] `ha-cli dashboards backup <url_path>` - Export to file
- [x] `ha-cli dashboards restore <file>` - Import from file
- [x] `ha-cli dashboards entities <url_path>` - Extract entity references
- [x] `ha-cli dashboards create <id> <url> <title>` - Create new dashboard
- [x] `ha-cli dashboards delete <id>` - Delete dashboard
- [x] `ha-cli dashboards views <url_path>` - List views in dashboard

### Phase 3: Entity Renaming Features ✅
**Duration**: 2-3 days  
**Status**: Complete (Exceeded Plan)

#### 3.1 Entity Scanner
- [x] Create entity scanning functionality:
  - [x] Walk dashboard JSON/YAML structure
  - [x] Find entity references in:
    - Card `entity` fields
    - Card `entities` arrays
    - Action configurations
    - Template strings
  - [x] Build entity usage map
  - [x] Cross-domain analysis (automations + dashboards)

#### 3.2 Entity Renamer
- [x] Create entity renaming functionality:
  - [x] Accept regex patterns for search/replace
  - [x] Walk and replace all references
  - [x] Preserve structure and formatting
  - [x] Generate change report
  - [x] Dry-run mode support

#### 3.3 Rename CLI Command
- [x] Implemented as `ha-cli entities` domain:
  ```bash
  # Regex-based rename
  ha-cli entities rename \
    --search "^climate\.(.*)(?<!_ac)$" \
    --replace "climate.\1_ac" \
    --dry-run
  
  # Import bulk operations from CSV
  ha-cli entities import-operations operations.csv
  
  # Analyze entity usage across domains
  ha-cli entities analyze climate.master_bedroom
  ```

#### 3.4 Cross-Domain Integration
- [x] Implemented full `ha-cli entities` domain
- [x] Integrated entity operations across automations and dashboards
- [x] Replaced ha-rename tool functionality

### Phase 4: Testing & Documentation
**Duration**: 1-2 days  
**Status**: Partially Complete

#### 4.1 Test Suite
- [ ] **Unit Tests**:
  - [ ] Dashboard model parsing/serialization
  - [ ] Entity scanner accuracy
  - [ ] Storage manager operations
- [ ] **Integration Tests**:
  - [ ] WebSocket dashboard operations
  - [ ] Entity renaming scenarios
  - [ ] YAML preservation
- [ ] **End-to-End Tests**:
  - [ ] Full rename workflow
  - [ ] Backup/restore cycle

#### 4.2 Documentation Updates
- [ ] Update README.md:
  - [ ] New project name and description
  - [ ] Dashboard commands
  - [ ] Entity renaming guide
  - [ ] Migration from ha-automation
- [ ] Create DASHBOARDS.md with:
  - [ ] Storage types explanation
  - [ ] Entity reference locations
  - [ ] Best practices
- [ ] Update CLAUDE.md with learnings

#### 4.3 Migration Support
- [ ] Create migration guide
- [ ] Add deprecation notices to ha-automation
- [ ] Update shell completions
- [ ] Test backward compatibility

## Technical Considerations

### Entity Reference Patterns

Dashboards contain entity references in many locations:

```yaml
# Direct entity reference
- type: entity
  entity: sensor.temperature

# Entity arrays
- type: entities
  entities:
    - sensor.temperature
    - sensor.humidity

# In actions
- type: button
  tap_action:
    action: call-service
    service: light.turn_on
    target:
      entity_id: light.bedroom

# In templates
- type: markdown
  content: "Temperature: {{ states('sensor.temperature') }}"
```

### Storage Detection

Like automations, dashboards have two storage modes:
1. **Storage mode**: Check WebSocket for available dashboards
2. **YAML mode**: Check `configuration.yaml` for `lovelace: mode: yaml`

### Change Safety

1. **Backup First**: Always create backup before modifications
2. **Validation**: Check entities exist before renaming
3. **Dry Run**: Show changes before applying
4. **Atomic Operations**: All-or-nothing updates

## Success Metrics

- [ ] All existing automation commands work unchanged
- [ ] Dashboard CRUD operations work for both storage types
- [ ] Entity renaming correctly updates all references
- [ ] Performance: Process 100KB dashboard in < 1 second
- [ ] Zero data loss during operations

## Dependencies

- Existing ha-automation-cli codebase
- Home Assistant WebSocket API
- Python 3.11+ (consistent with current requirements)

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing users | Keep ha-automation command working |
| Dashboard format changes | Version detection and compatibility |
| Large dashboards (>1MB) | Streaming JSON parser if needed |
| Missing entity references | Comprehensive scanner with tests |
| YAML formatting loss | Use ruamel.yaml preservation |

## Next Steps

### Priority 1: Complete Automation Commands
The following commands exist in `ha_automation/cli.py` but need to be migrated to `ha_cli/domains/automations/cli.py`:
- [ ] `create` - Create new automation from YAML file
- [ ] `update` - Update existing automation
- [ ] `delete` - Delete automation
- [ ] `enable` - Enable automation
- [ ] `disable` - Disable automation
- [ ] `reload` - Reload all automations
- [ ] `monitor` - Monitor automation events in real-time
- [ ] `migrate` - Migrate automation between storage types (UI ↔ file)
- [ ] `test_trigger` - Test automation triggers
- [ ] `events` - Monitor events
- [ ] `control` - Control automations

### Priority 2: Testing & Documentation
- [ ] Complete unit tests for all domains
- [ ] Add integration tests
- [ ] Update all documentation
- [ ] Create migration guide from ha-automation to ha-cli

### Priority 3: Future Domains
Once the automation commands are complete:

1. **Scripts Domain**: `ha-cli scripts`
2. **Scenes Domain**: `ha-cli scenes`  
3. **Areas Domain**: `ha-cli areas`
4. **Devices Domain**: `ha-cli devices`

## References

- [ADR-0001: Transform to Multi-Domain CLI](docs/adr/ADR-0001-transform-to-multi-domain-cli.md)
- [Dashboard WebSocket Research](../../../CLAUDE.md)
- [Existing ha-automation-cli v2 plan](plan-automation-v2.md.bak)