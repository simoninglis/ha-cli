#!/usr/bin/env python3
"""Test script to list all automations via WebSocket."""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from ha_cli.common.client import HAClient


def format_automation_state(state: dict) -> dict:
    """Format automation state for display."""
    entity_id = state.get("entity_id", "")
    attributes = state.get("attributes", {})
    
    # Extract automation ID from entity_id
    automation_id = entity_id.replace("automation.", "")
    
    return {
        "id": automation_id,
        "entity_id": entity_id,
        "name": attributes.get("friendly_name", automation_id),
        "state": state.get("state", "unknown"),
        "last_triggered": attributes.get("last_triggered"),
        "mode": attributes.get("mode", "single"),
        "current": attributes.get("current", 0),
        "max": attributes.get("max", 10),
    }


async def main():
    """Main function to list automations."""
    # Load configuration from .mcp.json
    mcp_config_path = Path(__file__).parent.parent.parent / ".mcp.json"
    
    if not mcp_config_path.exists():
        print(f"Error: .mcp.json not found at {mcp_config_path}")
        sys.exit(1)
    
    with open(mcp_config_path) as f:
        config = json.load(f)
    
    # Extract URL and token
    ha_config = config.get("mcpServers", {}).get("home-assistant", {})
    url = ha_config.get("env", {}).get("HOME_ASSISTANT_URL")
    
    # Extract token from args - it's after "Bearer" in the args list
    args = ha_config.get("args", [])
    token = None
    for i, arg in enumerate(args):
        if arg.startswith("Bearer "):
            token = arg.replace("Bearer ", "")
            break
    
    if not url or not token:
        print("Error: Could not extract URL or token from .mcp.json")
        sys.exit(1)
    
    print(f"Connecting to Home Assistant at {url}")
    print("=" * 80)
    
    # Connect to Home Assistant
    async with HAClient(url, token) as client:
        try:
            # Get all automation states via WebSocket
            print("Fetching automation states via WebSocket...")
            automation_states = await client.get_automation_states()
            
            if not automation_states:
                print("No automations found.")
                return
            
            print(f"\nFound {len(automation_states)} automations:\n")
            
            # Sort by entity_id
            automation_states.sort(key=lambda x: x.get("entity_id", ""))
            
            # Display automations
            for state in automation_states:
                automation = format_automation_state(state)
                
                print(f"ID: {automation['id']}")
                print(f"Name: {automation['name']}")
                print(f"State: {automation['state']}")
                print(f"Mode: {automation['mode']}")
                
                if automation['last_triggered']:
                    # Parse and format the last triggered time
                    try:
                        last_triggered = datetime.fromisoformat(
                            automation['last_triggered'].replace('Z', '+00:00')
                        )
                        print(f"Last Triggered: {last_triggered.strftime('%Y-%m-%d %H:%M:%S')}")
                    except:
                        print(f"Last Triggered: {automation['last_triggered']}")
                else:
                    print("Last Triggered: Never")
                
                if automation['current'] > 0:
                    print(f"Currently Running: {automation['current']}/{automation['max']}")
                
                print("-" * 40)
            
            # Summary
            enabled_count = sum(1 for s in automation_states if s.get("state") == "on")
            disabled_count = sum(1 for s in automation_states if s.get("state") == "off")
            
            print(f"\nSummary:")
            print(f"  Total: {len(automation_states)}")
            print(f"  Enabled: {enabled_count}")
            print(f"  Disabled: {disabled_count}")
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())