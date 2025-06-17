#!/usr/bin/env python3
"""Discover and analyze automation types in Home Assistant."""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path to import our modules
sys.path.insert(0, str(Path(__file__).parent))

from ha_automation.client import HAClient


async def discover_automations():
    """Discover all automations and their types."""
    # Get connection details from environment or use defaults
    url = os.environ.get("HA_URL", "http://10.0.20.35:8123")
    token = os.environ.get("HA_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZDk1YzEyMDkxNWM0ZTVlYmQ5ZTNjNTFhMWEyNjliZSIsImlhdCI6MTc0OTgzMTA2NCwiZXhwIjoyMDY1MTkxMDY0fQ.DzcpavvQW7OvUwjufRoK-8KWeoy0oTrx68M78tJB2K8")
    
    print(f"Connecting to {url}...")
    
    async with HAClient(url, token) as client:
        # Get all automation entities
        print("\n1. Getting all automation entities...")
        states = await client.get_automation_states()
        
        print(f"Found {len(states)} total automations\n")
        
        ui_automations = []
        file_automations = []
        unknown_automations = []
        
        # Test each automation to determine its type
        for state in states:
            entity_id = state.get("entity_id", "")
            attrs = state.get("attributes", {})
            friendly_name = attrs.get("friendly_name", entity_id)
            
            print(f"Checking {entity_id}...")
            
            # Try to read config via WebSocket
            try:
                await client._ensure_ws_connected()
                msg_id = client._ws_id + 1
                client._ws_id = msg_id
                
                message = {
                    "id": msg_id,
                    "type": "automation/config",
                    "entity_id": entity_id
                }
                
                await client._ws.send(json.dumps(message))
                
                # Wait for response with timeout
                response_received = False
                start_time = asyncio.get_event_loop().time()
                
                while asyncio.get_event_loop().time() - start_time < 5:  # 5 second timeout
                    try:
                        msg = await asyncio.wait_for(client._ws.recv(), timeout=1.0)
                        data = json.loads(msg)
                        
                        if data.get("id") == msg_id:
                            response_received = True
                            if data.get("success"):
                                config = data.get("result", {}).get("config", {})
                                
                                # Check if it has an ID (UI-style automations have 32-char hex IDs)
                                automation_id = config.get("id", "")
                                
                                # Check format
                                has_plural = "triggers" in config or "conditions" in config or "actions" in config
                                has_singular = "trigger" in config or "condition" in config or "action" in config
                                
                                info = {
                                    "entity_id": entity_id,
                                    "friendly_name": friendly_name,
                                    "id": automation_id,
                                    "id_length": len(automation_id),
                                    "has_plural_format": has_plural,
                                    "has_singular_format": has_singular,
                                    "state": state.get("state"),
                                    "last_triggered": attrs.get("last_triggered", "Never")
                                }
                                
                                # Categorize based on ID format and structure
                                if len(automation_id) == 32 and automation_id.isalnum():
                                    ui_automations.append(info)
                                else:
                                    file_automations.append(info)
                            else:
                                # Failed to get config
                                unknown_automations.append({
                                    "entity_id": entity_id,
                                    "friendly_name": friendly_name,
                                    "error": data.get("error", {}).get("message", "Unknown error"),
                                    "state": state.get("state"),
                                    "last_triggered": attrs.get("last_triggered", "Never")
                                })
                            break
                    except asyncio.TimeoutError:
                        continue
                
                if not response_received:
                    unknown_automations.append({
                        "entity_id": entity_id,
                        "friendly_name": friendly_name,
                        "error": "Timeout waiting for response",
                        "state": state.get("state")
                    })
                    
            except Exception as e:
                unknown_automations.append({
                    "entity_id": entity_id,
                    "friendly_name": friendly_name,
                    "error": str(e),
                    "state": state.get("state")
                })
        
        # Print results
        print("\n" + "="*60)
        print("AUTOMATION DISCOVERY RESULTS")
        print("="*60)
        
        print(f"\n📱 UI-STYLE AUTOMATIONS ({len(ui_automations)}):")
        print("  (32-char hex IDs, stored in .storage/automations)")
        for auto in ui_automations[:5]:  # Show first 5
            print(f"\n  • {auto['entity_id']}")
            print(f"    Name: {auto['friendly_name']}")
            print(f"    ID: {auto['id']}")
            print(f"    Format: {'Plural (triggers/actions)' if auto['has_plural_format'] else 'Singular (trigger/action)'}")
            print(f"    State: {auto['state']}")
            print(f"    Last triggered: {auto['last_triggered']}")
        if len(ui_automations) > 5:
            print(f"\n  ... and {len(ui_automations) - 5} more")
        
        print(f"\n📄 FILE-BASED AUTOMATIONS ({len(file_automations)}):")
        print("  (Custom IDs or no IDs, likely in automations.yaml)")
        for auto in file_automations[:5]:  # Show first 5
            print(f"\n  • {auto['entity_id']}")
            print(f"    Name: {auto['friendly_name']}")
            print(f"    ID: {auto['id'] or 'None'}")
            print(f"    Format: {'Plural (triggers/actions)' if auto['has_plural_format'] else 'Singular (trigger/action)'}")
            print(f"    State: {auto['state']}")
            print(f"    Last triggered: {auto['last_triggered']}")
        if len(file_automations) > 5:
            print(f"\n  ... and {len(file_automations) - 5} more")
        
        if unknown_automations:
            print(f"\n❓ UNKNOWN/ERROR AUTOMATIONS ({len(unknown_automations)}):")
            for auto in unknown_automations[:3]:
                print(f"\n  • {auto['entity_id']}")
                print(f"    Name: {auto['friendly_name']}")
                print(f"    Error: {auto['error']}")
        
        # Summary
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"Total automations: {len(states)}")
        print(f"UI-style (with hex IDs): {len(ui_automations)}")
        print(f"File-based (custom/no IDs): {len(file_automations)}")
        print(f"Unknown/errors: {len(unknown_automations)}")
        
        # Test file system access
        print("\n" + "="*60)
        print("FILE SYSTEM CHECK")
        print("="*60)
        
        # Check if we can access the REST endpoint for listing
        print("\nTesting REST API list endpoint...")
        try:
            # Try the endpoint our current implementation uses
            result = await client._rest("GET", "/api/config/automation/config")
            print(f"✅ REST list endpoint works! Got {len(result)} automations")
        except Exception as e:
            print(f"❌ REST list endpoint failed: {e}")
            print(f"   Error type: {type(e).__name__}")


if __name__ == "__main__":
    asyncio.run(discover_automations())