#!/usr/bin/env python3
"""Test entity sanitization directly"""

import asyncio
import os
import sys
import json
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Add the package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ha_cli.common.client import HAClient
from ha_cli.domains.entities.models import Entity


async def test():
    """Test entity sanitization"""
    # Test data with embedded newlines
    test_state = {
        "entity_id": "button.office_downlights_idle_power_management_load_error\nstatus",
        "state": "unknown",
        "attributes": {
            "friendly_name": "Office Downlights Idle Power Management Load error \nstatus"
        }
    }
    
    print("Original data:")
    print(f"entity_id has newline: {'\\n' in test_state['entity_id']}")
    print(f"friendly_name has newline: {'\\n' in test_state['attributes']['friendly_name']}")
    
    # Create Entity object
    entity = Entity.from_ha_state(test_state)
    
    print("\nAfter Entity creation:")
    print(f"entity_id has newline: {'\\n' in entity.entity_id}")
    print(f"friendly_name has newline: {'\\n' in entity.friendly_name}")
    
    # Convert to dict
    entity_dict = entity.to_dict()
    
    print("\nAfter to_dict():")
    print(f"entity_id has newline: {'\\n' in entity_dict['entity_id']}")
    print(f"friendly_name has newline: {'\\n' in entity_dict['friendly_name']}")
    
    # Try JSON serialization
    try:
        json_str = json.dumps(entity_dict, indent=2)
        print("\nJSON serialization successful!")
        # Verify no newlines in values
        parsed = json.loads(json_str)
        print(f"Parsed entity_id has newline: {'\\n' in parsed['entity_id']}")
        print(f"Parsed friendly_name has newline: {'\\n' in parsed['friendly_name']}")
    except Exception as e:
        print(f"\nJSON serialization failed: {e}")
    
    # Now test with real HA data
    print("\n\nTesting with real Home Assistant data:")
    client = HAClient(
        os.environ.get('HOME_ASSISTANT_URL', 'http://10.0.20.35:8123'),
        os.environ.get('HOME_ASSISTANT_TOKEN', os.environ.get('HA_TOKEN'))
    )
    
    async with client:
        states = await client.get_states()
        
        # Find the problematic entity
        for state in states:
            if 'button.office_downlights_idle_power_management_load_error' in state.get('entity_id', ''):
                print(f"\nFound problematic entity: {repr(state['entity_id'])}")
                print(f"Raw entity_id length: {len(state['entity_id'])}")
                entity = Entity.from_ha_state(state)
                entity_dict = entity.to_dict()
                
                # Check for newlines
                print(f"Entity object - entity_id: {repr(entity.entity_id)}")
                print(f"Entity object - entity_id length: {len(entity.entity_id)}")
                print(f"Entity object - entity_id has newline: {'\\n' in entity.entity_id}")
                print(f"Entity dict - entity_id has newline: {'\\n' in entity_dict['entity_id']}")
                
                # Print the actual JSON
                print("\nJSON output:")
                print(json.dumps(entity_dict, indent=2))
                break


if __name__ == '__main__':
    asyncio.run(test())