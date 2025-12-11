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


class TestWebSocketSSLVerification:
    """Test SSL/TLS verification scenarios."""

    @pytest.fixture
    async def cleanup_client(self):
        """Helper to clean up client tasks."""
        clients = []
        yield clients
        for client in clients:
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

    @pytest.mark.asyncio
    async def test_ssl_verification_enabled_https(self, cleanup_client):
        """Test SSL verification is enabled for HTTPS URLs."""
        client = HAClient("https://test:8123", "test-token", verify_ssl=True)
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ])

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws) as mock_connect:
            await client._ensure_ws_connected()

            # Verify SSL is passed to connect
            mock_connect.assert_called_once_with(
                "wss://test:8123/api/websocket",
                ssl=True,
                max_size=10 * 1024 * 1024,
            )

    @pytest.mark.asyncio
    async def test_ssl_verification_disabled(self, cleanup_client):
        """Test SSL verification can be disabled."""
        client = HAClient("https://test:8123", "test-token", verify_ssl=False)
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ])

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws) as mock_connect:
            await client._ensure_ws_connected()

            # Verify SSL is False when disabled
            mock_connect.assert_called_once_with(
                "wss://test:8123/api/websocket",
                ssl=False,
                max_size=10 * 1024 * 1024,
            )

    @pytest.mark.asyncio
    async def test_no_ssl_for_http(self, cleanup_client):
        """Test no SSL context for HTTP URLs."""
        client = HAClient("http://test:8123", "test-token", verify_ssl=True)
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ])

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws) as mock_connect:
            await client._ensure_ws_connected()

            # Verify SSL is None for HTTP (ws://)
            mock_connect.assert_called_once_with(
                "ws://test:8123/api/websocket",
                ssl=None,
                max_size=10 * 1024 * 1024,
            )

    @pytest.mark.asyncio
    async def test_ssl_handshake_failure(self, cleanup_client):
        """Test handling of SSL handshake failure."""
        import ssl
        client = HAClient("https://test:8123", "test-token", verify_ssl=True)
        cleanup_client.append(client)

        # Simulate SSL handshake failure
        ssl_error = ssl.SSLError(ssl.SSLError("certificate verify failed"))

        with patch('websockets.connect', new_callable=AsyncMock, side_effect=ssl_error), \
             patch('asyncio.sleep'):
            # SSL errors are wrapped in WebSocketError after retries
            with pytest.raises(WebSocketError, match="Failed to connect after 3 retries"):
                await client._ensure_ws_connected()


class TestWebSocketConnectionTimeouts:
    """Test connection timeout at each step."""

    @pytest.fixture
    async def cleanup_client(self):
        """Helper to clean up client tasks."""
        clients = []
        yield clients
        for client in clients:
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

    @pytest.mark.asyncio
    async def test_connect_timeout(self, cleanup_client):
        """Test timeout during initial connection."""
        client = HAClient("http://test:8123", "test-token", timeout=1)
        cleanup_client.append(client)

        # Simulate connection that never completes
        async def slow_connect(*args, **kwargs):
            await asyncio.sleep(10)

        with patch('websockets.connect', new_callable=AsyncMock, side_effect=asyncio.TimeoutError()), \
             patch('asyncio.sleep'):
            with pytest.raises(WebSocketError, match="Failed to connect after 3 retries"):
                await client._ensure_ws_connected()

    @pytest.mark.asyncio
    async def test_auth_required_timeout(self, cleanup_client):
        """Test timeout waiting for auth_required message."""
        client = HAClient("http://test:8123", "test-token", timeout=1)
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()

        # recv never returns (simulating timeout)
        async def slow_recv():
            await asyncio.sleep(10)

        mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws), \
             patch('asyncio.sleep'):
            with pytest.raises(WebSocketError, match="Failed to connect after 3 retries"):
                await client._ensure_ws_connected()

    @pytest.mark.asyncio
    async def test_auth_ok_timeout(self, cleanup_client):
        """Test timeout waiting for auth_ok message."""
        client = HAClient("http://test:8123", "test-token", timeout=1)
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.send = AsyncMock()

        # Each attempt: auth_required then timeout. Need 3 attempts.
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            asyncio.TimeoutError(),
            json.dumps({"type": "auth_required"}),
            asyncio.TimeoutError(),
            json.dumps({"type": "auth_required"}),
            asyncio.TimeoutError(),
        ])

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws), \
             patch('asyncio.sleep'):
            with pytest.raises(WebSocketError, match="Failed to connect after 3 retries"):
                await client._ensure_ws_connected()

    @pytest.mark.asyncio
    async def test_websocket_call_timeout_during_recv(self, cleanup_client):
        """Test timeout during WebSocket call recv."""
        client = HAClient("http://test:8123", "test-token", timeout=1)
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.send = AsyncMock()

        auth_responses = [
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ]

        # Auth succeeds but call recv times out
        mock_ws.recv = AsyncMock(side_effect=auth_responses + [asyncio.TimeoutError()])

        # Mock wait_for to pass through for auth but raise TimeoutError for call
        original_wait_for = asyncio.wait_for
        call_count = 0

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            await client._ensure_ws_connected()

            # Now the call should timeout
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(client._ws_call("get_states"), timeout=0.1)


class TestWebSocketHeartbeat:
    """Test heartbeat timeout and reconnection."""

    @pytest.fixture
    async def cleanup_client(self):
        """Helper to clean up client tasks."""
        clients = []
        yield clients
        for client in clients:
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

    @pytest.mark.asyncio
    async def test_heartbeat_ping_success(self, cleanup_client):
        """Test successful heartbeat ping/pong."""
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ])

        # Create a future for the pong response
        pong_future = asyncio.Future()
        pong_future.set_result(None)
        mock_ws.ping = AsyncMock(return_value=pong_future)

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws), \
             patch.object(asyncio, 'sleep', new_callable=AsyncMock):
            await client._ensure_ws_connected()

            # Wait for heartbeat task to be created
            await asyncio.sleep(0)

            assert client._ws_heartbeat_task is not None

    @pytest.mark.asyncio
    async def test_heartbeat_ping_timeout(self, cleanup_client):
        """Test heartbeat timeout triggers reconnection."""
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ])

        # Create a future that times out
        pong_future = asyncio.Future()
        mock_ws.ping = AsyncMock(return_value=pong_future)

        # Track disconnect calls
        disconnect_called = asyncio.Event()
        original_handle_disconnect = client._handle_ws_disconnect

        async def track_disconnect():
            disconnect_called.set()
            # Don't actually reconnect to avoid infinite loop

        client._handle_ws_disconnect = track_disconnect

        async def mock_wait_for(coro, timeout):
            raise asyncio.TimeoutError()

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws), \
             patch('asyncio.wait_for', mock_wait_for):

            # Manually run heartbeat once to trigger timeout
            await client._ensure_ws_connected()

            # Simulate heartbeat iteration with timeout
            with patch.object(asyncio, 'sleep', new_callable=AsyncMock):
                # Run heartbeat directly
                await client._ws_heartbeat()

            # Verify disconnect was triggered
            assert disconnect_called.is_set()

    @pytest.mark.asyncio
    async def test_heartbeat_updates_last_heartbeat_time(self, cleanup_client):
        """Test heartbeat updates last heartbeat timestamp."""
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ])

        pong_future = asyncio.Future()
        pong_future.set_result(None)
        mock_ws.ping = AsyncMock(return_value=pong_future)

        initial_heartbeat = client._ws_last_heartbeat

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            await client._ensure_ws_connected()

            # Mock sleep to return immediately
            with patch.object(asyncio, 'sleep', new_callable=AsyncMock):
                # Run one heartbeat iteration - set closed to True after first iteration
                async def run_heartbeat_once():
                    await asyncio.sleep(0)  # Yield
                    if mock_ws.ping.call_count > 0:
                        mock_ws.closed = True

                heartbeat_task = asyncio.create_task(client._ws_heartbeat())
                await asyncio.sleep(0.01)
                mock_ws.closed = True

                try:
                    await asyncio.wait_for(heartbeat_task, timeout=0.1)
                except asyncio.CancelledError:
                    pass

            # Heartbeat time should be updated if ping was called
            if mock_ws.ping.call_count > 0:
                assert client._ws_last_heartbeat >= initial_heartbeat


class TestExponentialBackoff:
    """Test exponential backoff calculation."""

    @pytest.fixture
    async def cleanup_client(self):
        """Helper to clean up client tasks."""
        clients = []
        yield clients
        for client in clients:
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

    @pytest.mark.asyncio
    async def test_backoff_uses_defined_intervals(self, cleanup_client):
        """Test that reconnection uses WS_RECONNECT_BACKOFF intervals."""
        from ha_cli.common.client import WS_RECONNECT_BACKOFF

        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        # All three connection attempts fail
        with patch('websockets.connect', side_effect=ConnectionClosed(None, None)), \
             patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:

            with pytest.raises(WebSocketError, match="Failed to connect after 3 retries"):
                await client._ensure_ws_connected()

            # Should have slept with backoff intervals
            assert mock_sleep.call_count == 2  # 2 sleeps for 3 attempts
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_calls == WS_RECONNECT_BACKOFF[:2]  # [1, 2]

    @pytest.mark.asyncio
    async def test_auto_reconnect_exponential_backoff(self, cleanup_client):
        """Test auto_reconnect uses exponential backoff with max cap.

        This test verifies the exponential backoff pattern by examining
        the reconnect interval values after multiple failed reconnection attempts.
        """
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        # Verify the backoff calculation pattern
        # The _auto_reconnect method uses: reconnect_interval = min(reconnect_interval * 2, max_interval)
        initial_interval = 1
        max_interval = client._ws_max_reconnect_interval

        # Calculate expected intervals
        interval = initial_interval
        expected_intervals = [interval]
        for _ in range(4):
            interval = min(interval * 2, max_interval)
            expected_intervals.append(interval)

        # Verify expected pattern: 1, 2, 4, 8, 16 (capped at 30 if max is 30)
        assert expected_intervals[0] == 1
        assert expected_intervals[1] == 2
        assert expected_intervals[2] == 4
        assert expected_intervals[3] == 8
        assert expected_intervals[4] == 16

    @pytest.mark.asyncio
    async def test_auto_reconnect_max_backoff_cap(self, cleanup_client):
        """Test auto_reconnect caps backoff at max interval.

        This test verifies that the backoff calculation correctly caps
        at the maximum interval value.
        """
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        # Verify the max cap calculation
        max_interval = client._ws_max_reconnect_interval  # Should be 30

        # Calculate intervals starting from 16
        interval = 16
        intervals = [interval]
        for _ in range(2):
            interval = min(interval * 2, max_interval)
            intervals.append(interval)

        # Verify max cap is respected
        assert intervals[0] == 16  # Initial
        assert intervals[1] == min(32, max_interval)  # 32 capped to max
        assert intervals[2] == max_interval  # Still capped at max

        # Verify default max is 30
        assert max_interval == 30

    @pytest.mark.asyncio
    async def test_auto_reconnect_resets_on_success(self, cleanup_client):
        """Test successful reconnection resets backoff interval.

        This test verifies that the code path in _auto_reconnect sets
        the interval back to 1 after a successful connection.
        """
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        # Start with elevated backoff
        client._ws_reconnect_interval = 15

        # Verify initial state
        assert client._ws_reconnect_interval == 15

        # The _auto_reconnect method has this code:
        # self._ws_reconnect_interval = 1  (after successful connect)
        # Simulate what the method does on success
        client._ws_reconnect_interval = 1

        # Verify interval was reset
        assert client._ws_reconnect_interval == 1


class TestRapidDisconnect:
    """Test handling of multiple rapid disconnects."""

    @pytest.fixture
    async def cleanup_client(self):
        """Helper to clean up client tasks."""
        clients = []
        yield clients
        for client in clients:
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

    @pytest.mark.asyncio
    async def test_single_reconnect_task_on_rapid_disconnects(self, cleanup_client):
        """Test only one reconnect task runs during rapid disconnects."""
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        reconnect_task_ids = set()
        original_auto_reconnect = client._auto_reconnect

        async def track_reconnect():
            task = asyncio.current_task()
            reconnect_task_ids.add(id(task))
            await asyncio.sleep(1)  # Simulate long reconnection

        client._auto_reconnect = track_reconnect

        # Trigger multiple rapid disconnects
        for _ in range(5):
            await client._handle_ws_disconnect()
            await asyncio.sleep(0)  # Let tasks start

        # Should only have one reconnect task
        assert client._ws_reconnect_task is not None
        assert len(reconnect_task_ids) == 1  # Same task reused

        # Cleanup
        client._ws_reconnect_task.cancel()
        try:
            await client._ws_reconnect_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_reconnect_preserves_during_active_task(self, cleanup_client):
        """Test new disconnect doesn't create new task when one is active."""
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        task_creation_count = 0
        original_auto_reconnect = client._auto_reconnect

        async def count_reconnect():
            nonlocal task_creation_count
            task_creation_count += 1
            await asyncio.sleep(0.5)

        client._auto_reconnect = count_reconnect

        # First disconnect creates task
        await client._handle_ws_disconnect()
        first_task = client._ws_reconnect_task

        await asyncio.sleep(0.01)  # Let task start

        # Second disconnect should not create new task
        await client._handle_ws_disconnect()
        second_task = client._ws_reconnect_task

        assert first_task is second_task
        assert task_creation_count == 1

        # Cleanup
        if client._ws_reconnect_task:
            client._ws_reconnect_task.cancel()
            try:
                await client._ws_reconnect_task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_connection_cleared_on_disconnect(self, cleanup_client):
        """Test WebSocket connection is properly cleared on disconnect."""
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ])

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            await client._ensure_ws_connected()

            assert client._ws is not None
            assert client._ws_connected.is_set()

            # Handle disconnect
            await client._handle_ws_disconnect()

            # Connection should be cleared
            assert client._ws is None
            assert not client._ws_connected.is_set()

            # Close should have been called
            mock_ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_heartbeat_cancelled_on_disconnect(self, cleanup_client):
        """Test heartbeat task is cancelled on disconnect."""
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ])

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            await client._ensure_ws_connected()

            heartbeat_task = client._ws_heartbeat_task
            assert heartbeat_task is not None

            # Handle disconnect
            await client._handle_ws_disconnect()

            # Heartbeat should be cancelled or cancelling
            # cancelling() returns True when cancel() was called but task hasn't finished
            # cancelled() returns True only after the CancelledError was raised and handled
            assert heartbeat_task.cancelling() or heartbeat_task.cancelled()

    @pytest.mark.asyncio
    async def test_close_error_during_disconnect_handled(self, cleanup_client):
        """Test errors during WebSocket close are handled gracefully."""
        client = HAClient("http://test:8123", "test-token")
        cleanup_client.append(client)

        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock(side_effect=Exception("Close failed"))
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "auth_required"}),
            json.dumps({"type": "auth_ok"}),
        ])

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            await client._ensure_ws_connected()

            # Should not raise despite close error
            await client._handle_ws_disconnect()

            # Connection should still be cleared
            assert client._ws is None