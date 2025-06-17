#!/usr/bin/env python3
"""Test raw WebSocket data"""

import asyncio
import json
import os
from dotenv import load_dotenv

load_dotenv()

import websockets

async def test():
    """Get raw WebSocket data"""
    url = os.environ.get('HOME_ASSISTANT_URL', 'http://10.0.20.35:8123')
    token = os.environ.get('HOME_ASSISTANT_TOKEN')
    
    ws_url = url.replace('http', 'ws') + '/api/websocket'
    
    async with websockets.connect(ws_url, max_size=10*1024*1024) as ws:  # 10MB
        # Auth flow
        auth_req = await ws.recv()
        print(f"Auth request: {auth_req}")
        
        await ws.send(json.dumps({
            "type": "auth",
            "access_token": token
        }))
        
        auth_result = await ws.recv()
        print(f"Auth result: {auth_result}")
        
        # Get states
        await ws.send(json.dumps({
            "id": 1,
            "type": "get_states"
        }))
        
        result = await ws.recv()
        data = json.loads(result)
        
        # Find problematic entity
        if data.get('type') == 'result' and data.get('success'):
            for state in data.get('result', []):
                if 'button.office_downlights_idle_power_management_load_error' in state.get('entity_id', ''):
                    print(f"\nFound entity:")
                    print(f"Raw entity_id: {repr(state['entity_id'])}")
                    print(f"Has newline at start: {state['entity_id'].startswith('\\n')}")
                    print(f"Has newline anywhere: {'\\n' in state['entity_id']}")
                    print(f"Entity ID bytes: {state['entity_id'].encode('utf-8')}")
                    break

if __name__ == '__main__':
    asyncio.run(test())