#!/usr/bin/env python3
"""Test sanitization directly"""

import asyncio
import os
import sys
import json

# Add the package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ha_cli.common.client import HAClient


async def test():
    """Test getting entities and check sanitization"""
    client = HAClient(
        os.environ.get('HOME_ASSISTANT_URL', 'http://10.0.20.35:8123'),
        os.environ.get('HOME_ASSISTANT_TOKEN', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZDk1YzEyMDkxNWM0ZTVlYmQ5ZTNjNTFhMWEyNjliZSIsImlhdCI6MTc0OTgzMTA2NCwiZXhwIjoyMDY1MTkxMDY0fQ.DzcpavvQW7OvUwjufRoK-8KWeoy0oTrx68M78tJB2K8')
    )
    
    async with client:
        states = await client.get_states()
        
        # Find problematic entity
        for state in states:
            if 'button.office_downlights_idle_power_management_load_error' in state.get('entity_id', ''):
                print(f"Found entity: {state['entity_id']}")
                print(f"Entity has newline: {repr('\\n' in state['entity_id'])}")
                print(f"Friendly name: {repr(state.get('attributes', {}).get('friendly_name', ''))}")
                print(f"Friendly name has newline: {'\\n' in state.get('attributes', {}).get('friendly_name', '')}")
                
                # Try to serialize
                try:
                    json_str = json.dumps(state, indent=2)
                    print("JSON serialization successful")
                    # Check if JSON has control chars
                    if '\n' in state.get('attributes', {}).get('friendly_name', ''):
                        print("ERROR: Attributes still have newlines after sanitization!")
                except Exception as e:
                    print(f"JSON serialization failed: {e}")
                break


if __name__ == '__main__':
    asyncio.run(test())