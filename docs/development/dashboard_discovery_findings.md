# Dashboard Discovery Findings

## Summary

The climate dashboard at `/lovelace/climate` is not being discovered by `lovelace/dashboards/list` because it's not a separate dashboard - it's a **view (tab)** within the default Lovelace dashboard.

## Key Findings

### 1. Two Types of Dashboard Organization

Home Assistant has two levels of dashboard organization:

1. **Dashboards** - Top-level navigation items shown in the sidebar
   - Each has its own URL path (e.g., `/lovelace/dashboard-master`)
   - Listed by the `lovelace/dashboards/list` WebSocket command
   - Can be created/managed separately

2. **Views** - Tabs within a dashboard
   - Part of a dashboard's configuration
   - Accessed via paths like `/lovelace/climate` (for the default dashboard)
   - NOT listed by `lovelace/dashboards/list`

### 2. Dashboard Discovery Methods

#### Current Method (Incomplete)
- `lovelace/dashboards/list` - Returns only separate dashboards, not views

#### Complete Discovery Requires:
1. **Get all panels**: Use `get_panels` WebSocket command
2. **Get dashboard configs**: For each Lovelace panel, get its configuration
3. **Extract views**: Each dashboard config contains views with their paths

### 3. API Endpoints Analysis

#### Working WebSocket Commands:
- `get_panels` - Returns ALL panels including all Lovelace dashboards
- `lovelace/dashboards/list` - Returns only non-default dashboards
- `lovelace/config` - Gets default dashboard config (includes all views)
- `lovelace/config` with `url_path` - Gets specific dashboard config

#### Non-existent REST API Endpoints:
- `/api/panels` - 404
- `/api/panel_config` - 404
- `/api/lovelace/dashboards` - 404
- `/api/lovelace/config` - 404

### 4. The Climate Dashboard Case

The climate dashboard is actually:
- A view in the default Lovelace dashboard
- Path: `climate` (accessed as `/lovelace/climate`)
- Index: 10 in the views array
- Contains 10 cards with climate entities

## Implementation Recommendations

### 1. Update Dashboard Service

Add a method to discover ALL dashboards including views:

```python
async def list_all_dashboard_locations(self) -> dict:
    """List all dashboard locations including views within dashboards."""
    
    # Get all panels
    panels = await self.client._ws_call("get_panels")
    
    locations = {
        "dashboards": [],
        "views": {}
    }
    
    # Process each Lovelace panel
    for panel_id, panel_data in panels.items():
        if panel_data.get("component_name") == "lovelace":
            url_path = panel_data.get("url_path")
            
            # Add dashboard info
            dashboard_info = {
                "id": panel_id,
                "url_path": url_path,
                "title": panel_data.get("title", "Default" if panel_id == "lovelace" else "Untitled"),
                "is_default": panel_id == "lovelace"
            }
            locations["dashboards"].append(dashboard_info)
            
            # Get views for this dashboard
            try:
                config_url = None if panel_id == "lovelace" else url_path
                config = await self.client.get_dashboard_config(config_url)
                
                views = []
                for view in config.get("views", []):
                    views.append({
                        "title": view.get("title", "Untitled"),
                        "path": view.get("path", ""),
                        "full_path": f"/lovelace/{view.get('path', '')}" if panel_id == "lovelace" 
                                    else f"/{url_path}/{view.get('path', '')}"
                    })
                
                locations["views"][panel_id] = views
                
            except Exception as e:
                logger.warning(f"Could not get config for dashboard {panel_id}: {e}")
    
    return locations
```

### 2. Update CLI Commands

Add options to the dashboards command:

```bash
# List all dashboards (current behavior)
ha-cli dashboards list

# List all dashboards AND their views
ha-cli dashboards list --include-views

# Search for entities across all dashboards and views
ha-cli dashboards entities --all-views
```

### 3. Update HAClient

Add the `get_panels` method to HAClient:

```python
async def get_panels(self) -> dict[str, Any]:
    """Get all UI panels via WebSocket.
    
    Returns:
        Dictionary of panel_id -> panel_data
    """
    return await self._ws_call("get_panels")
```

## Testing Results

Found 9 Lovelace dashboards via `get_panels`:
- 1 default dashboard (`lovelace`) with multiple views including climate
- 8 custom dashboards (room-specific)

The `lovelace/dashboards/list` only returns the 8 custom dashboards, missing the default dashboard and all views within dashboards.