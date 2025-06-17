#!/usr/bin/env python3
"""Test if sanitization affects operations"""

import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ha_cli.common.client import HAClient
from ha_cli.domains.entities.service import EntityService


async def test():
    """Test if sanitized entity IDs work for operations"""
    client = HAClient(
        os.environ.get('HOME_ASSISTANT_URL'),
        os.environ.get('HOME_ASSISTANT_TOKEN')
    )
    
    async with client:
        service = EntityService(client)
        
        # Get all entities
        entities = await service.list_entities()
        
        # Check if any entity IDs were modified by sanitization
        modified_count = 0
        for entity in entities:
            # Get raw state to compare
            states = await client.get_states()
            for state in states:
                if state['entity_id'] == entity.entity_id:
                    break
            else:
                # Try with potential control characters
                for state in states:
                    raw_id = state['entity_id']
                    if raw_id.strip() == entity.entity_id or \
                       raw_id.replace('\n', '').replace('\t', '') == entity.entity_id:
                        print(f"MODIFIED: {repr(raw_id)} -> {repr(entity.entity_id)}")
                        modified_count += 1
                        
                        # Test if we can still get the entity
                        result = await service.get_entity(entity.entity_id)
                        if result:
                            print(f"  - get_entity with sanitized ID: SUCCESS")
                        else:
                            print(f"  - get_entity with sanitized ID: FAILED!")
                        break
        
        print(f"\nTotal entities with modified IDs: {modified_count}")


if __name__ == '__main__':
    asyncio.run(test())