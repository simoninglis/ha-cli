"""Tests for WebSocket client functionality."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from ha_automation.client import HAClient
from ha_automation.exceptions import AuthenticationError, TimeoutError, WebSocketError


class TestWebSocketClient:
    """Test WebSocket client functionality."""
    
    @pytest.fixture
    async def client(self):
        """Create test client."""
        client = HAClient("http://test:8123", "test-token")
        yield client
        # Cleanup tasks
        if hasattr(client, '_ws_heartbeat_task') and client._ws_heartbeat_task:
            client._ws_heartbeat_task.cancel()
            try:
                await client._ws_heartbeat_task
            except asyncio.CancelledError:
                pass
        if hasattr(client, '_ws_reconnect_task') and client._ws_reconnect_task:
            client._ws_reconnect_task.cancel()
            try:
                await client._ws_reconnect_task
            except asyncio.CancelledError:
                pass
    
    @pytest.fixture
    def mock_websocket(self):
        """Create mock WebSocket connection."""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock()
        return mock_ws
    
    @pytest.mark.asyncio
    async def test_websocket_connection_success(self, client, mock_websocket):
        """Test successful WebSocket connection and authentication."""
        # Mock the connection process
        mock_websocket.recv.side_effect = [
            json.dumps({"type": "auth_required", "ha_version": "2025.6.0"}),
            json.dumps({"type": "auth_ok", "ha_version": "2025.6.0"}),
        ]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            await client._ensure_ws_connected()
            
            # Verify connection was made with correct parameters
            websockets.connect.assert_called_once_with(
                "ws://test:8123/api/websocket",
                ssl=None,
                max_size=10 * 1024 * 1024,
            )
            
            # Verify authentication was sent
            auth_call = mock_websocket.send.call_args_list[0]
            auth_msg = json.loads(auth_call[0][0])
            assert auth_msg["type"] == "auth"
            assert auth_msg["access_token"] == "test-token"
    
    @pytest.mark.asyncio
    async def test_websocket_auth_failure(self, client, mock_websocket):
        """Test WebSocket authentication failure."""
        mock_websocket.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_invalid", "message": "Invalid token"}),
        ]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            with pytest.raises(AuthenticationError, match="Invalid access token"):
                await client._ensure_ws_connected()
    
    @pytest.mark.asyncio
    async def test_websocket_reconnection(self, client, mock_websocket):
        """Test WebSocket reconnection logic."""
        # First two attempts fail, third succeeds
        connect_side_effects = [
            ConnectionClosed(None, None),
            ConnectionClosed(None, None),
            mock_websocket,
        ]
        
        mock_websocket.recv.side_effect = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        with patch('websockets.connect', new_callable=AsyncMock, side_effect=connect_side_effects), \
             patch('asyncio.sleep') as mock_sleep:
            
            await client._ensure_ws_connected()
            
            # Should have retried twice
            assert websockets.connect.call_count == 3
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(1)  # First retry
            mock_sleep.assert_any_call(2)  # Second retry
    
    @pytest.mark.asyncio
    async def test_websocket_max_retries_exceeded(self, client):
        """Test WebSocket connection fails after max retries."""
        with patch('websockets.connect', side_effect=ConnectionClosed(None, None)), \
             patch('asyncio.sleep'):
            
            with pytest.raises(WebSocketError, match="Failed to connect after 3 retries"):
                await client._ensure_ws_connected()
    
    @pytest.mark.asyncio
    async def test_subscribe_events(self, client, mock_websocket):
        """Test event subscription."""
        # Setup authentication
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        # Setup subscription response
        sub_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })
        
        # Setup event data
        event1 = json.dumps({
            "id": 1,
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "automation.test",
                    "old_state": {"state": "on"},
                    "new_state": {"state": "off"}
                }
            }
        })
        
        event2 = json.dumps({
            "id": 1,
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "automation.test2",
                    "old_state": {"state": "off"},
                    "new_state": {"state": "on"}
                }
            }
        })
        
        mock_websocket.recv.side_effect = auth_responses + [sub_response, event1, event2]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            events = []
            async for event in client.subscribe_events("state_changed"):
                events.append(event)
                if len(events) >= 2:
                    break
            
            assert len(events) == 2
            assert events[0]["data"]["entity_id"] == "automation.test"
            assert events[1]["data"]["entity_id"] == "automation.test2"
    
    @pytest.mark.asyncio
    async def test_subscribe_automation_events(self, client, mock_websocket):
        """Test automation-specific event subscription."""
        # Setup responses
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        sub_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
        })
        
        # Mix of automation and non-automation events
        events = [
            json.dumps({
                "id": 1,
                "type": "event",
                "event": {
                    "event_type": "state_changed",
                    "data": {"entity_id": "automation.test", "new_state": {"state": "on"}}
                }
            }),
            json.dumps({
                "id": 1,
                "type": "event",
                "event": {
                    "event_type": "state_changed",
                    "data": {"entity_id": "light.living_room", "new_state": {"state": "on"}}
                }
            }),
            json.dumps({
                "id": 1,
                "type": "event",
                "event": {
                    "event_type": "state_changed",
                    "data": {"entity_id": "automation.test2", "new_state": {"state": "off"}}
                }
            }),
        ]
        
        mock_websocket.recv.side_effect = auth_responses + [sub_response] + events
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            automation_events = []
            async for event in client.subscribe_automation_events():
                automation_events.append(event)
                if len(automation_events) >= 2:
                    break
            
            # Should only get automation events
            assert len(automation_events) == 2
            assert all(e["data"]["entity_id"].startswith("automation.") for e in automation_events)
    
    @pytest.mark.asyncio
    async def test_subscribe_trigger(self, client, mock_websocket):
        """Test trigger subscription."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        sub_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
        })
        
        trigger_event = json.dumps({
            "id": 1,
            "type": "event",
            "event": {
                "variables": {
                    "trigger": {
                        "platform": "time",
                        "at": "07:00:00",
                        "now": "2025-06-13T07:00:00"
                    }
                }
            }
        })
        
        mock_websocket.recv.side_effect = auth_responses + [sub_response, trigger_event]
        
        trigger_config = {"platform": "time", "at": "07:00:00"}
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            events = []
            async for event in client.subscribe_trigger(trigger_config):
                events.append(event)
                break
            
            assert len(events) == 1
            assert events[0]["variables"]["trigger"]["platform"] == "time"
    
    @pytest.mark.asyncio
    async def test_get_states(self, client, mock_websocket):
        """Test getting all states."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        states_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": [
                {
                    "entity_id": "automation.test",
                    "state": "on",
                    "attributes": {"friendly_name": "Test Automation"}
                },
                {
                    "entity_id": "light.living_room",
                    "state": "off",
                    "attributes": {"friendly_name": "Living Room Light"}
                }
            ]
        })
        
        mock_websocket.recv.side_effect = auth_responses + [states_response]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                states = await client.get_states()
                
                assert len(states) == 2
                assert states[0]["entity_id"] == "automation.test"
                assert states[1]["entity_id"] == "light.living_room"
    
    @pytest.mark.asyncio
    async def test_get_automation_states(self, client, mock_websocket):
        """Test getting only automation states."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        states_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": [
                {"entity_id": "automation.test", "state": "on"},
                {"entity_id": "light.living_room", "state": "off"},
                {"entity_id": "automation.test2", "state": "off"},
                {"entity_id": "switch.bedroom", "state": "on"},
            ]
        })
        
        mock_websocket.recv.side_effect = auth_responses + [states_response]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                states = await client.get_automation_states()
                
                assert len(states) == 2
                assert all(s["entity_id"].startswith("automation.") for s in states)
    
    @pytest.mark.asyncio
    async def test_call_automation_service(self, client, mock_websocket):
        """Test calling automation services."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        service_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": {"context": {"id": "test123"}}
        })
        
        mock_websocket.recv.side_effect = auth_responses + [service_response]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                await client.call_automation_service(
                    "turn_on",
                    ["automation.test", "automation.test2"]
                )
                
                # Check the service call
                service_call = mock_websocket.send.call_args_list[-1]
                msg = json.loads(service_call[0][0])
                
                assert msg["type"] == "call_service"
                assert msg["domain"] == "automation"
                assert msg["service"] == "turn_on"
                assert msg["service_data"]["entity_id"] == ["automation.test", "automation.test2"]
    
    @pytest.mark.asyncio
    async def test_call_automation_service_single_entity(self, client, mock_websocket):
        """Test calling automation service with single entity ID."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        service_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": {}
        })
        
        mock_websocket.recv.side_effect = auth_responses + [service_response]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                await client.call_automation_service("trigger", "automation.test")
                
                # Check service call
                service_call = mock_websocket.send.call_args_list[-1]
                msg = json.loads(service_call[0][0])
                
                assert msg["service"] == "trigger"
                assert msg["service_data"]["entity_id"] == ["automation.test"]
    
    @pytest.mark.asyncio
    async def test_event_subscription_cleanup(self, client, mock_websocket):
        """Test that event subscriptions are properly cleaned up."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        sub_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
        })
        
        # Simulate connection closed during iteration
        mock_websocket.recv.side_effect = auth_responses + [sub_response, ConnectionClosedError(None, None)]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            events_received = 0
            with pytest.raises(ConnectionClosedError):
                async for _ in client.subscribe_events():
                    events_received += 1
            
            # Connection was lost, so no unsubscribe should be sent
            # (since the connection is gone)
            assert events_received == 0  # No events were yielded before error
    
    @pytest.mark.asyncio
    async def test_websocket_heartbeat(self, client, mock_websocket):
        """Test WebSocket heartbeat mechanism."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        mock_websocket.recv.side_effect = auth_responses
        mock_websocket.ping = AsyncMock(return_value=asyncio.Future())
        mock_websocket.ping.return_value.set_result(None)
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            await client._ensure_ws_connected()
            
            # Wait a bit for heartbeat task to start
            await asyncio.sleep(0.1)
            
            # Verify heartbeat task is running
            assert client._ws_heartbeat_task is not None
            assert not client._ws_heartbeat_task.done()
            
            # Cleanup
            client._ws_heartbeat_task.cancel()
            try:
                await client._ws_heartbeat_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_websocket_auto_reconnect(self, client, mock_websocket):
        """Test automatic reconnection on connection loss."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        # First connection succeeds, then fails, then succeeds again
        mock_websocket.recv.side_effect = auth_responses + [
            ConnectionClosedError(None, None),  # Connection lost
        ] + auth_responses  # Reconnection
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket), \
             patch('asyncio.sleep'):
            
            await client._ensure_ws_connected()
            
            # Simulate connection loss
            await client._handle_ws_disconnect()
            
            # Verify reconnection task was started
            assert client._ws_reconnect_task is not None
    
    @pytest.mark.asyncio
    async def test_wait_for_connection(self, client, mock_websocket):
        """Test waiting for connection to be established."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        mock_websocket.recv.side_effect = auth_responses
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            # Start connection in background
            connect_task = asyncio.create_task(client._ensure_ws_connected())
            
            # Wait for connection
            await client.wait_for_connection(timeout=5)
            
            # Verify connection is established
            assert client._ws_connected.is_set()
            
            await connect_task
    
    @pytest.mark.asyncio
    async def test_wait_for_connection_timeout(self, client):
        """Test timeout when waiting for connection."""
        # Don't connect at all
        with pytest.raises(TimeoutError, match="WebSocket connection not established"):
            await client.wait_for_connection(timeout=0.1)
    
    @pytest.mark.asyncio
    async def test_connection_recovery_during_call(self, client, mock_websocket):
        """Test connection recovery during WebSocket call."""
        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]
        
        # Connection fails during call
        mock_websocket.recv.side_effect = auth_responses + [
            ConnectionClosedError(None, None),  # Connection lost during call
        ]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(WebSocketError, match="Connection lost during WebSocket call"):
                    await client.enable_automation("test")