# Home Assistant Integration Guide

This document captures key learnings, constraints, and best practices discovered while building the ha-cli tool for Home Assistant integration.

## API Constraints and Workarounds

### REST API Limitations
1. **Config Integration Required**: The `/api/config/automation/config` endpoint requires the `config` integration to be enabled
   - Not all Home Assistant installations have this enabled
   - Always implement WebSocket fallbacks for critical functionality

2. **Limited Configuration Access**: 
   - File-based automations: Read-only via API (no direct file system access)
   - UI automations: Full CRUD support via REST API
   - Dashboard YAML mode: Read-only via API

### WebSocket API Characteristics
1. **Large Payload Sizes**: Set `max_size=10*1024*1024` (10MB) for WebSocket connections
   - Default 1MB limit is too small for installations with many entities
   - Example: `websockets.connect(ws_url, max_size=10*1024*1024)`

2. **Entity States vs Full Config**:
   - WebSocket can list all entities but not full automation configurations
   - Use `get_states` for entity information
   - Some operations only available via REST

3. **Authentication Flow**:
   ```python
   # Always follow this sequence:
   1. Wait for auth_required message
   2. Send auth with access token
   3. Wait for auth_ok before proceeding
   ```

## Data Quality Issues

### Control Characters in Entity IDs
**Discovery**: Home Assistant can return entity IDs and friendly names with embedded control characters (newlines, tabs, etc.)

**Example**: `button.office_downlights_idle_power_management_load_error\nstatus`

**Important**: The issue was NOT with the data itself, but with how Python's `print()` function was handling the output.

### Best Practices for Data Handling
1. **Preserve Original Data**: Don't over-sanitize
   - Only remove truly invalid characters (like NULL bytes)
   - Keep formatting characters that might be intentional
   - Let Home Assistant handle its own data validation

2. **Output Methods Matter**:
   ```python
   # DON'T use print() for structured output:
   print(json.dumps(data, indent=2))  # Can modify output!
   
   # DO use sys.stdout.write():
   import sys
   json_str = json.dumps(data, indent=2)
   sys.stdout.write(json_str)
   sys.stdout.write('\n')
   sys.stdout.flush()
   ```

## Integration Patterns

### Multi-Method Access Strategy
When accessing automation configurations:

1. **Primary**: Try REST API first
2. **Fallback 1**: Use WebSocket for basic entity states
3. **Fallback 2**: Attempt File Editor API access (if available)
4. **Fallback 3**: Pattern-based analysis using entity naming

Example implementation:
```python
async def get_automation_config(self, automation_id):
    try:
        # Method 1: REST API
        return await self.client.get_automation(automation_id)
    except NotFoundError:
        # Method 2: WebSocket state
        states = await self.client.get_automation_states()
        # ... extract what we can from state data
```

### Entity Reference Detection
When analyzing entity usage across automations and dashboards:

1. **Direct References**: Look for `entity_id`, `entity_ids` fields
2. **Service Targets**: Check `target.entity_id`, `target.entity_ids`
3. **Dashboard Cards**: Search for `entity`, `entities` in card configs
4. **Nested Structures**: Recursively search all dictionary/list structures

## Performance Considerations

### Batch Operations
- Use WebSocket for bulk entity retrieval (single large request)
- Implement progress indicators for operations on many entities
- Consider pagination for very large result sets

### Connection Management
- Reuse WebSocket connections where possible
- Implement automatic reconnection with exponential backoff
- Handle connection timeouts gracefully

## Testing and Debugging

### Debugging Output Issues
1. **Check raw bytes**: Use `od -c` to see actual characters
2. **Write to file**: Bypass stdout to isolate issues
3. **Use repr()**: See exact string contents
4. **Test minimal examples**: Reduce complexity to find root cause

### Common Pitfalls
1. **Assuming clean data**: Always be prepared for unexpected characters
2. **Over-engineering solutions**: The simplest fix is often correct
3. **Not testing with real data**: Mock data may not reflect reality

## Home Assistant Specifics

### Entity Naming Patterns
- Climate entities often include location but not "_ac" suffix
- Automation IDs use underscores, aliases use spaces
- Domain must match when renaming entities

### Storage Types
- **UI Storage**: `/config/.storage/automations.yaml` (JSON format)
- **File Storage**: `/config/automations.yaml` (YAML format)
- **Dashboard Storage**: Can be in `.storage` (UI) or YAML files

### Rate Limiting
- No documented rate limits on local Home Assistant instances
- Be mindful of system resources with bulk operations
- Implement reasonable delays for mass updates

## Integration Checklist

When building Home Assistant integrations:

- [ ] Handle both REST and WebSocket APIs
- [ ] Set appropriate WebSocket max_size
- [ ] Use sys.stdout.write() for structured output
- [ ] Implement proper error handling with fallbacks
- [ ] Test with real Home Assistant data
- [ ] Support both UI and file-based configurations
- [ ] Handle authentication properly
- [ ] Document API limitations and workarounds