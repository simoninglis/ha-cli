#!/usr/bin/env python3
"""Test WebSocket automation/config command for UI-style automations."""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path to import our modules
sys.path.insert(0, str(Path(__file__).parent))

from ha_automation.client import HAClient


async def test_automation_config():
    """Test reading automation config via WebSocket."""
    # Get connection details from environment or use defaults
    url = os.environ.get("HA_URL", "http://10.0.20.35:8123")
    token = os.environ.get("HA_TOKEN", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZDk1YzEyMDkxNWM0ZTVlYmQ5ZTNjNTFhMWEyNjliZSIsImlhdCI6MTc0OTgzMTA2NCwiZXhwIjoyMDY1MTkxMDY0fQ.DzcpavvQW7OvUwjufRoK-8KWeoy0oTrx68M78tJB2K8")
    
    print(f"Connecting to {url}...")
    
    async with HAClient(url, token) as client:
        # First, get all automation entities
        print("\n1. Getting all automation entities...")
        states = await client.get_automation_states()
        
        if not states:
            print("No automations found!")
            return
        
        print(f"Found {len(states)} automations:")
        for state in states[:5]:  # Show first 5
            entity_id = state.get("entity_id", "unknown")
            friendly_name = state.get("attributes", {}).get("friendly_name", entity_id)
            print(f"  - {entity_id}: {friendly_name}")
        
        # Now test the automation/config command
        print("\n2. Testing automation/config WebSocket command...")
        
        # Pick the first automation
        test_entity = states[0]["entity_id"]
        print(f"\nTrying to read config for: {test_entity}")
        
        try:
            # Try the automation/config command as described in the research
            await client._ensure_ws_connected()
            
            # Send the command
            msg_id = client._ws_id + 1
            client._ws_id = msg_id
            
            message = {
                "id": msg_id,
                "type": "automation/config",
                "entity_id": test_entity
            }
            
            print(f"Sending: {json.dumps(message, indent=2)}")
            await client._ws.send(json.dumps(message))
            
            # Wait for response
            while True:
                msg = await client._ws.recv()
                data = json.loads(msg)
                
                if data.get("id") == msg_id:
                    print(f"\nReceived response:")
                    print(json.dumps(data, indent=2))
                    
                    if data.get("type") == "result" and data.get("success"):
                        config = data.get("result", {}).get("config", {})
                        if config:
                            print("\n✅ SUCCESS! Automation config retrieved:")
                            print(f"  - ID: {config.get('id', 'N/A')}")
                            print(f"  - Alias: {config.get('alias', 'N/A')}")
                            print(f"  - Mode: {config.get('mode', 'N/A')}")
                            print(f"  - Has triggers: {'triggers' in config or 'trigger' in config}")
                            print(f"  - Has actions: {'actions' in config or 'action' in config}")
                            
                            # Check format - plural vs singular
                            if 'triggers' in config:
                                print("  - Format: UI-style (uses 'triggers', 'conditions', 'actions')")
                            else:
                                print("  - Format: File-style (uses 'trigger', 'condition', 'action')")
                    break
                    
        except Exception as e:
            print(f"\n❌ Error testing automation/config: {e}")
            print(f"Error type: {type(e).__name__}")
        
        # Also try a different approach - get states with attributes
        print("\n3. Checking automation attributes for config info...")
        for state in states[:3]:
            entity_id = state.get("entity_id", "")
            attrs = state.get("attributes", {})
            print(f"\n{entity_id}:")
            print(f"  - ID: {attrs.get('id', 'N/A')}")
            print(f"  - Friendly name: {attrs.get('friendly_name', 'N/A')}")
            print(f"  - Last triggered: {attrs.get('last_triggered', 'Never')}")


if __name__ == "__main__":
    asyncio.run(test_automation_config())