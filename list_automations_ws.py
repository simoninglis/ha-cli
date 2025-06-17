#!/usr/bin/env python3
"""List all automations via WebSocket with filtering and formatting options."""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

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


def filter_automations(automations: list[dict], args: argparse.Namespace) -> list[dict]:
    """Filter automations based on command-line arguments."""
    filtered = automations
    
    # Filter by state
    if args.state:
        filtered = [a for a in filtered if a.get("state") == args.state]
    
    # Filter by name/ID
    if args.filter:
        filter_lower = args.filter.lower()
        filtered = [
            a for a in filtered
            if filter_lower in a["name"].lower() or filter_lower in a["id"].lower()
        ]
    
    # Filter by last triggered
    if args.triggered:
        filtered = [a for a in filtered if a["last_triggered"] is not None]
    elif args.never_triggered:
        filtered = [a for a in filtered if a["last_triggered"] is None]
    
    # Filter by currently running
    if args.running:
        filtered = [a for a in filtered if a["current"] > 0]
    
    return filtered


def output_table(automations: list[dict]) -> None:
    """Output automations in table format."""
    if not automations:
        print("No automations found matching criteria.")
        return
    
    # Calculate column widths
    id_width = max(len(a["id"]) for a in automations)
    name_width = min(50, max(len(a["name"]) for a in automations))
    
    # Header
    print(f"{'ID':<{id_width}} | {'Name':<{name_width}} | {'State':<8} | {'Mode':<10} | Last Triggered")
    print("-" * (id_width + name_width + 50))
    
    # Rows
    for automation in automations:
        name = automation["name"]
        if len(name) > name_width:
            name = name[:name_width-3] + "..."
        
        last_triggered = "Never"
        if automation["last_triggered"]:
            try:
                dt = datetime.fromisoformat(automation["last_triggered"].replace('Z', '+00:00'))
                last_triggered = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                last_triggered = automation["last_triggered"]
        
        running = ""
        if automation["current"] > 0:
            running = f" [{automation['current']}/{automation['max']}]"
        
        print(f"{automation['id']:<{id_width}} | {name:<{name_width}} | {automation['state']:<8} | {automation['mode']:<10} | {last_triggered}{running}")


def output_json(automations: list[dict]) -> None:
    """Output automations as JSON."""
    print(json.dumps(automations, indent=2))


def output_simple(automations: list[dict]) -> None:
    """Output automations in simple format (just IDs)."""
    for automation in automations:
        print(automation["id"])


def output_detailed(automations: list[dict]) -> None:
    """Output automations in detailed format."""
    for i, automation in enumerate(automations):
        if i > 0:
            print("-" * 40)
        
        print(f"ID: {automation['id']}")
        print(f"Name: {automation['name']}")
        print(f"State: {automation['state']}")
        print(f"Mode: {automation['mode']}")
        
        if automation['last_triggered']:
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


async def main():
    """Main function to list automations."""
    parser = argparse.ArgumentParser(description="List Home Assistant automations via WebSocket")
    
    # Filtering options
    parser.add_argument("--state", choices=["on", "off"], help="Filter by state (on/off)")
    parser.add_argument("--filter", "-f", help="Filter by name or ID (case insensitive)")
    parser.add_argument("--triggered", action="store_true", help="Show only triggered automations")
    parser.add_argument("--never-triggered", action="store_true", help="Show only never-triggered automations")
    parser.add_argument("--running", action="store_true", help="Show only currently running automations")
    
    # Output format options
    parser.add_argument("--format", choices=["table", "json", "simple", "detailed"], 
                       default="table", help="Output format (default: table)")
    
    # Sorting options
    parser.add_argument("--sort", choices=["id", "name", "state", "last_triggered"], 
                       default="id", help="Sort by field (default: id)")
    parser.add_argument("--reverse", action="store_true", help="Reverse sort order")
    
    args = parser.parse_args()
    
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
    args_list = ha_config.get("args", [])
    token = None
    for i, arg in enumerate(args_list):
        if arg.startswith("Bearer "):
            token = arg.replace("Bearer ", "")
            break
    
    if not url or not token:
        print("Error: Could not extract URL or token from .mcp.json")
        sys.exit(1)
    
    # Connect to Home Assistant
    async with HAClient(url, token) as client:
        try:
            # Get all automation states via WebSocket
            automation_states = await client.get_automation_states()
            
            # Format automations
            automations = [format_automation_state(state) for state in automation_states]
            
            # Filter automations
            automations = filter_automations(automations, args)
            
            # Sort automations
            if args.sort == "id":
                automations.sort(key=lambda x: x["id"], reverse=args.reverse)
            elif args.sort == "name":
                automations.sort(key=lambda x: x["name"], reverse=args.reverse)
            elif args.sort == "state":
                automations.sort(key=lambda x: x["state"], reverse=args.reverse)
            elif args.sort == "last_triggered":
                # Sort with None values at the end
                def sort_key(x):
                    if x["last_triggered"] is None:
                        return datetime.min if args.reverse else datetime.max
                    try:
                        return datetime.fromisoformat(x["last_triggered"].replace('Z', '+00:00'))
                    except:
                        return datetime.min
                automations.sort(key=sort_key, reverse=args.reverse)
            
            # Output results
            if args.format == "table":
                output_table(automations)
            elif args.format == "json":
                output_json(automations)
            elif args.format == "simple":
                output_simple(automations)
            elif args.format == "detailed":
                output_detailed(automations)
            
            # Summary
            if args.format in ["table", "detailed"]:
                print(f"\nTotal: {len(automations)} automations")
                if not args.filter and not args.state and not args.triggered and not args.never_triggered and not args.running:
                    enabled_count = sum(1 for a in automations if a["state"] == "on")
                    disabled_count = sum(1 for a in automations if a["state"] == "off")
                    print(f"Enabled: {enabled_count}, Disabled: {disabled_count}")
            
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())