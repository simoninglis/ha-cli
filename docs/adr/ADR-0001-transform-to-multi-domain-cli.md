# ADR-0001: Transform ha-automation-cli to Multi-Domain ha-cli

## Status
Proposed

## Context

We need to manage entity renaming across multiple Home Assistant subsystems (automations, dashboards, scripts, scenes) to support a consistent naming convention migration. Currently, we have:

1. **ha-automation-cli**: Successfully manages automations with dual storage support
2. **ha-rename**: Bulk renames entities in Home Assistant
3. **Need**: Tool to update entity references in dashboards when entities are renamed

The dashboard architecture mirrors automations:
- **Storage mode**: JSON in `.storage/`, managed via WebSocket API (`lovelace/config`, `lovelace/config/save`)
- **YAML mode**: Plain files, edited directly

Entity references appear throughout dashboards in:
- Card configurations (`entity`, `entities[]`)
- Actions (`tap_action.entity`)
- Templates containing entity IDs

## Decision

Transform `ha-automation-cli` into a general-purpose `ha-cli` tool with domain-specific subcommands:

```
ha-cli
├── automations    (current functionality)
├── dashboards     (new)
├── entities       (future: integrate ha-rename)
├── scripts        (future)
└── scenes         (future)
```

### Key Design Principles

1. **Domain Isolation**: Each subsystem (automations, dashboards) gets its own module
2. **Shared Infrastructure**: Common WebSocket client, config management, storage patterns
3. **Backward Compatibility**: Keep `ha-automation` command working
4. **Extensibility**: Easy to add new domains without affecting existing ones

### Implementation Structure

```
ha_cli/
├── common/              # Shared infrastructure
│   ├── client.py       # WebSocket/REST client
│   ├── config.py       # Configuration management
│   └── storage/        # Common storage patterns
├── domains/            # Domain-specific implementations
│   ├── automations/    # Current automation code
│   └── dashboards/     # New dashboard code
└── cli.py             # Root CLI with subcommands
```

## Consequences

### Positive

1. **Unified Experience**: Single tool for all Home Assistant maintenance
2. **Code Reuse**: Leverage proven WebSocket patterns and dual storage architecture
3. **Cross-Domain Operations**: Enable entity renaming across all subsystems
4. **Maintainability**: Clear separation of concerns between domains
5. **Discovery**: Users find all functionality in one place

### Negative

1. **Larger Scope**: Tool becomes more complex overall
2. **Migration Effort**: Existing users need to adapt to new command structure
3. **Testing Surface**: More code paths to test and maintain
4. **Naming**: "ha-cli" is generic (but this aligns with tools like `gh`, `az`, etc.)

### Alternatives Considered

1. **Separate ha-dashboard-cli tool**
   - ❌ Duplicates infrastructure
   - ❌ Fragments user experience
   - ❌ Makes cross-domain operations harder

2. **Add dashboard commands to ha-automation**
   - ❌ Violates single responsibility principle
   - ❌ Confusing naming

3. **Create entity-rename-tool for all subsystems**
   - ❌ Limited scope
   - ❌ Doesn't leverage existing infrastructure
   - ❌ Can't handle subsystem-specific operations

## Implementation Plan

1. **Phase 1**: Refactor to multi-domain architecture (1-2 days)
2. **Phase 2**: Implement dashboard support (3-4 days)
3. **Phase 3**: Add entity renaming features (2-3 days)
4. **Phase 4**: Testing and documentation (1-2 days)

## References

- [Home Assistant WebSocket API](https://developers.home-assistant.io/docs/api/websocket/)
- [Lovelace WebSocket Implementation](https://github.com/home-assistant/core/blob/master/homeassistant/components/lovelace/websocket.py)
- Dashboard research showing storage patterns match automations exactly