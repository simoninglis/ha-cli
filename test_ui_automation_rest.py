#!/usr/bin/env python3
"""Test REST API endpoints for UI-style automations."""

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

# Add parent directory to path to import our modules
sys.path.insert(0, str(Path(__file__).parent))

from ha_automation.client import HAClient


async def test_ui_automation_crud():
    """Test CRUD operations for UI-style automations."""
    # Get connection details from environment (required)
    url = os.environ.get("HA_URL", "http://10.0.20.35:8123")
    token = os.environ.get("HA_TOKEN")
    if not token:
        print("Error: HA_TOKEN environment variable is required")
        return
    
    print(f"Connecting to {url}...")
    
    # Generate a 32-character hex UUID as required
    automation_id = uuid.uuid4().hex
    print(f"\nGenerated automation ID: {automation_id}")
    
    async with HAClient(url, token) as client:
        # Test 1: Create a new automation using the research-specified endpoint
        print("\n1. Testing CREATE automation with REST API...")
        
        test_automation = {
            "id": automation_id,
            "alias": "Test UI Automation from CLI",
            "description": "Created by test script to verify API",
            "triggers": [{
                "trigger": "time",
                "at": "03:00:00"
            }],
            "conditions": [],
            "actions": [{
                "action": "notify.persistent_notification",
                "data": {
                    "message": "Test automation triggered"
                }
            }],
            "mode": "single"
        }
        
        create_url = f"/api/config/automation/config/{automation_id}"
        print(f"POST to: {create_url}")
        print(f"Payload: {json.dumps(test_automation, indent=2)}")
        
        try:
            # Use raw REST method to test the exact endpoint
            response = await client._rest("POST", create_url, json_data=test_automation)
            print(f"\n✅ CREATE Success! Response: {response}")
            
            # Wait a moment for HA to process
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"\n❌ CREATE Failed: {e}")
            print(f"Error type: {type(e).__name__}")
            
            # Try alternate endpoint format (without the ID in body)
            print("\n1b. Trying alternate format (no ID in body)...")
            test_automation_no_id = test_automation.copy()
            del test_automation_no_id["id"]
            
            try:
                response = await client._rest("POST", create_url, json_data=test_automation_no_id)
                print(f"✅ CREATE Success with alternate format! Response: {response}")
                await asyncio.sleep(2)
            except Exception as e2:
                print(f"❌ Alternate format also failed: {e2}")
                return
        
        # Test 2: Read the automation back using WebSocket
        print("\n2. Reading automation back via WebSocket...")
        entity_id = f"automation.test_ui_automation_from_cli"
        
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
            
            while True:
                msg = await client._ws.recv()
                data = json.loads(msg)
                
                if data.get("id") == msg_id:
                    if data.get("success"):
                        config = data.get("result", {}).get("config", {})
                        print(f"✅ READ Success! Got config:")
                        print(f"  - Alias: {config.get('alias')}")
                        print(f"  - ID: {config.get('id')}")
                    else:
                        print(f"❌ READ Failed: {data}")
                    break
                    
        except Exception as e:
            print(f"❌ WebSocket read error: {e}")
        
        # Test 3: Update the automation
        print("\n3. Testing UPDATE automation...")
        
        updated_automation = test_automation.copy()
        updated_automation["alias"] = "Updated Test UI Automation"
        updated_automation["description"] = "Updated by test script"
        
        try:
            response = await client._rest("POST", create_url, json_data=updated_automation)
            print(f"✅ UPDATE Success! Response: {response}")
            await asyncio.sleep(1)
        except Exception as e:
            print(f"❌ UPDATE Failed: {e}")
        
        # Test 4: List automations to verify it exists
        print("\n4. Checking if automation appears in entity list...")
        
        states = await client.get_automation_states()
        found = False
        for state in states:
            if automation_id in state.get("entity_id", "") or "test_ui_automation" in state.get("entity_id", ""):
                print(f"✅ Found automation: {state.get('entity_id')}")
                print(f"  - State: {state.get('state')}")
                print(f"  - Friendly name: {state.get('attributes', {}).get('friendly_name')}")
                found = True
                break
        
        if not found:
            print("❌ Automation not found in entity list")
        
        # Test 5: Delete the automation
        print("\n5. Testing DELETE automation...")
        
        delete_url = f"/api/config/automation/config/{automation_id}"
        
        try:
            response = await client._rest("DELETE", delete_url)
            print(f"✅ DELETE Success! Response: {response}")
        except Exception as e:
            print(f"❌ DELETE Failed: {e}")
        
        print("\n✅ Test completed!")


if __name__ == "__main__":
    asyncio.run(test_ui_automation_crud())