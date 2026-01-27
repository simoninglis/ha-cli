"""Integration tests for HAClient."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
import websockets
from websockets.exceptions import ConnectionClosedError

from ha_cli.common.client import HAClient
from ha_cli.common.exceptions import (
    AuthenticationError,
    ConnectionError,
    HAServerError,
    NotFoundError,
    ValidationError,
    WebSocketError,
)


class TestHAClientIntegration:
    """Integration tests for HAClient."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return HAClient("http://test:8123", "test-token", timeout=5)
    
    @pytest.mark.asyncio
    async def test_context_manager(self, client):
        """Test client can be used as context manager."""
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_httpx.return_value = mock_client
            
            async with client as c:
                assert c is client
                assert client._client is mock_client
            
            mock_client.aclose.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rest_api_success(self, client):
        """Test successful REST API call."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"test": "data"}'
        mock_response.json.return_value = {"test": "data"}
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client
            
            async with client:
                result = await client._rest("GET", "/api/test")
                
                assert result == {"test": "data"}
                mock_client.request.assert_called_once_with(
                    method="GET",
                    url="http://test:8123/api/test",
                    json=None,
                    params=None,
                )
    
    @pytest.mark.asyncio
    async def test_rest_api_auth_error(self, client):
        """Test REST API authentication error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client
            
            async with client:
                with pytest.raises(AuthenticationError, match="Invalid or expired"):
                    await client._rest("GET", "/api/test")
    
    @pytest.mark.asyncio
    async def test_rest_api_not_found(self, client):
        """Test REST API not found error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client
            
            async with client:
                with pytest.raises(NotFoundError, match="Resource not found"):
                    await client._rest("GET", "/api/test")
    
    @pytest.mark.asyncio
    async def test_rest_api_validation_error(self, client):
        """Test REST API validation error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad request details"
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client
            
            async with client:
                with pytest.raises(ValidationError, match="Bad request"):
                    await client._rest("GET", "/api/test")
    
    @pytest.mark.asyncio
    async def test_rest_api_server_error(self, client):
        """Test REST API server error."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client
            
            async with client:
                with pytest.raises(HAServerError, match="Server error"):
                    await client._rest("GET", "/api/test")
    
    @pytest.mark.asyncio
    async def test_rest_api_timeout(self, client):
        """Test REST API timeout error."""
        from ha_cli.common.exceptions import TimeoutError
        
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.TimeoutException("Timeout", request=None)
            mock_httpx.return_value = mock_client
            
            async with client:
                with pytest.raises(TimeoutError, match="Request timed out"):
                    await client._rest("GET", "/api/test")
    
    @pytest.mark.asyncio
    async def test_rest_api_connection_error(self, client):
        """Test REST API connection error."""
        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.ConnectError("Connection failed")
            mock_httpx.return_value = mock_client
            
            async with client:
                with pytest.raises(ConnectionError, match="Failed to connect"):
                    await client._rest("GET", "/api/test")
    
    @pytest.mark.asyncio
    async def test_websocket_connection_and_auth(self, client):
        """Test WebSocket connection and authentication."""
        mock_ws = AsyncMock()
        
        # Mock WebSocket messages
        auth_required = json.dumps({"type": "auth_required"})
        auth_ok = json.dumps({"type": "auth_ok"})
        mock_ws.recv.side_effect = [auth_required, auth_ok]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            async with client:
                await client._ensure_ws_connected()
                
                # Check auth message was sent
                mock_ws.send.assert_called_once()
                sent_message = json.loads(mock_ws.send.call_args[0][0])
                assert sent_message["type"] == "auth"
                assert sent_message["access_token"] == "test-token"
    
    @pytest.mark.asyncio
    async def test_websocket_auth_invalid(self, client):
        """Test WebSocket authentication failure."""
        mock_ws = AsyncMock()
        
        auth_required = json.dumps({"type": "auth_required"})
        auth_invalid = json.dumps({"type": "auth_invalid"})
        mock_ws.recv.side_effect = [auth_required, auth_invalid]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            async with client:
                with pytest.raises(AuthenticationError, match="Invalid access token"):
                    await client._ensure_ws_connected()
    
    @pytest.mark.asyncio
    async def test_websocket_call_success(self, client):
        """Test successful WebSocket service call."""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()

        # Mock authentication flow
        auth_required = json.dumps({"type": "auth_required"})
        auth_ok = json.dumps({"type": "auth_ok"})

        # Mock service call response
        result_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": {"test": "success"}
        })

        # Add terminator for reader task graceful exit
        mock_ws.recv.side_effect = [auth_required, auth_ok, result_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            async with client:
                result = await client._ws_call("call_service", domain="test", service="test")

                assert result == {"test": "success"}
    
    @pytest.mark.asyncio
    async def test_websocket_call_error(self, client):
        """Test WebSocket service call error."""
        mock_ws = AsyncMock()
        mock_ws.closed = False
        mock_ws.close = AsyncMock()

        # Mock authentication flow
        auth_required = json.dumps({"type": "auth_required"})
        auth_ok = json.dumps({"type": "auth_ok"})

        # Mock service call error response
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {"code": "test_error", "message": "Test error message"}
        })

        # Add terminator for reader task graceful exit
        mock_ws.recv.side_effect = [auth_required, auth_ok, error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            async with client:
                with pytest.raises(WebSocketError, match="test_error: Test error message"):
                    await client._ws_call("call_service", domain="test", service="test")
    
    @pytest.mark.asyncio
    async def test_list_automations(self, client):
        """Test list_automations method."""
        # WebSocket returns entity states format
        expected_states = [
            {"entity_id": "automation.test1", "state": "on", "attributes": {"friendly_name": "Test 1", "mode": "single"}},
            {"entity_id": "automation.test2", "state": "on", "attributes": {"friendly_name": "Test 2", "mode": "single"}}
        ]

        with patch.object(client, 'get_states', return_value=expected_states) as mock_get_states:
            async with client:
                result = await client.get_automation_states()

                assert len(result) == 2
                mock_get_states.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_automation(self, client):
        """Test get_automation method (uses WebSocket via get_automation_config)."""
        automation_id = "test_automation"
        expected_data = {"config": {"id": automation_id, "alias": "Test", "trigger": [], "action": []}}

        with patch.object(client, '_ws_call', return_value=expected_data) as mock_ws_call:
            async with client:
                result = await client.get_automation(automation_id)

                assert result["id"] == automation_id
                mock_ws_call.assert_called_once_with(
                    "automation/config",
                    entity_id=f"automation.{automation_id}"
                )
    
    @pytest.mark.asyncio
    async def test_enable_automation(self, client):
        """Test enable_automation method."""
        automation_id = "test_automation"
        
        with patch.object(client, '_ws_call') as mock_ws_call:
            async with client:
                await client.enable_automation(automation_id)
                
                mock_ws_call.assert_called_once_with(
                    "call_service",
                    domain="automation",
                    service="turn_on",
                    service_data={"entity_id": f"automation.{automation_id}"}
                )
    
    @pytest.mark.asyncio
    async def test_disable_automation(self, client):
        """Test disable_automation method."""
        automation_id = "test_automation"
        
        with patch.object(client, '_ws_call') as mock_ws_call:
            async with client:
                await client.disable_automation(automation_id)
                
                mock_ws_call.assert_called_once_with(
                    "call_service",
                    domain="automation",
                    service="turn_off",
                    service_data={"entity_id": f"automation.{automation_id}"}
                )
    
    @pytest.mark.asyncio
    async def test_reload_automations(self, client):
        """Test reload_automations method."""
        with patch.object(client, '_ws_call') as mock_ws_call:
            async with client:
                await client.reload_automations()
                
                mock_ws_call.assert_called_once_with(
                    "call_service",
                    domain="automation",
                    service="reload"
                )
    
    @pytest.mark.asyncio
    async def test_websocket_retry_logic(self, client):
        """Test WebSocket connection retry logic."""
        mock_ws = AsyncMock()
        
        # First two attempts fail, third succeeds
        connect_side_effects = [
            websockets.exceptions.ConnectionClosed(None, None),
            websockets.exceptions.ConnectionClosed(None, None),
            mock_ws
        ]
        
        auth_required = json.dumps({"type": "auth_required"})
        auth_ok = json.dumps({"type": "auth_ok"})
        mock_ws.recv.side_effect = [auth_required, auth_ok]
        
        with patch('websockets.connect', new_callable=AsyncMock, side_effect=connect_side_effects), \
             patch('asyncio.sleep') as mock_sleep:
            
            async with client:
                await client._ensure_ws_connected()
                
                # Should have called sleep twice for backoff
                assert mock_sleep.call_count == 2
                mock_sleep.assert_any_call(1)  # First retry after 1s
                mock_sleep.assert_any_call(2)  # Second retry after 2s
    
    @pytest.mark.asyncio
    async def test_websocket_max_retries_exceeded(self, client):
        """Test WebSocket connection fails after max retries."""
        connect_side_effects = [
            websockets.exceptions.ConnectionClosed(None, None),
            websockets.exceptions.ConnectionClosed(None, None),
            websockets.exceptions.ConnectionClosed(None, None)
        ]

        with patch('websockets.connect', new_callable=AsyncMock, side_effect=connect_side_effects), \
             patch('asyncio.sleep'):

            async with client:
                with pytest.raises(WebSocketError, match="Failed to connect after 3 retries"):
                    await client._ensure_ws_connected()

    # REST API CRUD methods tests

    @pytest.mark.asyncio
    async def test_probe_automation_rest_api_available(self, client):
        """Test REST API probe when available."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{}'
        mock_response.json.return_value = {}

        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client

            async with client:
                result = await client.probe_automation_rest_api()
                assert result is True

    @pytest.mark.asyncio
    async def test_probe_automation_rest_api_unavailable(self, client):
        """Test REST API probe when unavailable (404)."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client

            async with client:
                result = await client.probe_automation_rest_api()
                assert result is False

    @pytest.mark.asyncio
    async def test_get_automation_numeric_id(self, client):
        """Test getting numeric ID for an automation."""
        expected_result = {
            "config": {
                "id": "1634454808159",
                "alias": "Test Automation",
                "trigger": [],
                "action": []
            }
        }

        with patch.object(client, '_ws_call', return_value=expected_result) as mock_ws_call:
            async with client:
                result = await client.get_automation_numeric_id("test_automation")

                assert result == "1634454808159"
                mock_ws_call.assert_called_once_with(
                    "automation/config",
                    entity_id="automation.test_automation"
                )

    @pytest.mark.asyncio
    async def test_get_automation_numeric_id_not_found(self, client):
        """Test getting numeric ID when automation not found."""
        with patch.object(client, '_ws_call', side_effect=WebSocketError("not_found")):
            async with client:
                result = await client.get_automation_numeric_id("nonexistent")
                assert result is None

    @pytest.mark.asyncio
    async def test_create_automation_rest(self, client):
        """Test creating automation via REST API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{}'
        mock_response.json.return_value = {}

        with patch('httpx.AsyncClient') as mock_httpx, \
             patch.object(client, 'reload_automations') as mock_reload:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_httpx.return_value = mock_client_instance

            async with client:
                config = {
                    "alias": "Test Automation",
                    "trigger": [{"platform": "time"}],
                    "action": [{"service": "light.turn_on"}]
                }
                result = await client.create_automation_rest(config)

                # Should return a numeric ID
                assert result.isdigit()
                # Should have made REST call
                mock_client_instance.request.assert_called()
                # Should have reloaded automations
                mock_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_automation_rest(self, client):
        """Test updating automation via REST API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{}'
        mock_response.json.return_value = {}

        with patch('httpx.AsyncClient') as mock_httpx, \
             patch.object(client, 'reload_automations') as mock_reload:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_httpx.return_value = mock_client_instance

            async with client:
                config = {
                    "alias": "Updated Automation",
                    "trigger": [{"platform": "time"}],
                    "action": [{"service": "light.turn_off"}]
                }
                await client.update_automation_rest("1234567890123", config)

                # Should have made REST call to correct endpoint
                call_args = mock_client_instance.request.call_args
                assert "/api/config/automation/config/1234567890123" in str(call_args)
                # Should have reloaded automations
                mock_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_automation_rest(self, client):
        """Test deleting automation via REST API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b''

        with patch('httpx.AsyncClient') as mock_httpx, \
             patch.object(client, 'reload_automations') as mock_reload:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_httpx.return_value = mock_client_instance

            async with client:
                await client.delete_automation_rest("1234567890123")

                # Should have made DELETE request
                call_args = mock_client_instance.request.call_args
                assert call_args[1]["method"] == "DELETE"
                assert "/api/config/automation/config/1234567890123" in str(call_args)
                # Should have reloaded automations
                mock_reload.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_automation_rest(self, client):
        """Test getting automation config via REST API."""
        expected_config = {
            "id": "1234567890123",
            "alias": "Test Automation",
            "trigger": [{"platform": "time"}],
            "action": [{"service": "light.turn_on"}]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = json.dumps(expected_config).encode()
        mock_response.json.return_value = expected_config

        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client_instance = AsyncMock()
            mock_client_instance.request.return_value = mock_response
            mock_httpx.return_value = mock_client_instance

            async with client:
                result = await client.get_automation_rest("1234567890123")

                assert result == expected_config
                call_args = mock_client_instance.request.call_args
                assert call_args[1]["method"] == "GET"
                assert "/api/config/automation/config/1234567890123" in str(call_args)

    # REST API expect_json parameter tests (Phase 0.1)

    @pytest.mark.asyncio
    async def test_rest_api_text_response(self, client):
        """Test REST API call returning text (expect_json=False)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'Hello World'
        mock_response.text = 'Hello World'

        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client

            async with client:
                result = await client._rest("POST", "/api/template", expect_json=False)

                assert result == "Hello World"
                assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_rest_api_json_decode_error(self, client):
        """Test REST API call when JSON decode fails but expect_json=True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'Not JSON content'
        mock_response.text = 'Not JSON content'
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)

        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client

            async with client:
                with pytest.raises(ValidationError, match="Expected JSON response"):
                    await client._rest("GET", "/api/test")

    @pytest.mark.asyncio
    async def test_rest_api_default_expect_json(self, client):
        """Test REST API call defaults to expect_json=True."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"key": "value"}'
        mock_response.json.return_value = {"key": "value"}

        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client

            async with client:
                result = await client._rest("GET", "/api/test")

                assert result == {"key": "value"}
                mock_response.json.assert_called_once()

    @pytest.mark.asyncio
    async def test_rest_api_empty_content(self, client):
        """Test REST API call with empty content returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b''

        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client

            async with client:
                result = await client._rest("DELETE", "/api/test")

                assert result is None

    @pytest.mark.asyncio
    async def test_rest_api_error_message_extraction_json(self, client):
        """Test error message is extracted from JSON response body."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = '{"message": "Template syntax error: unexpected end"}'
        mock_response.json.return_value = {"message": "Template syntax error: unexpected end"}

        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client

            async with client:
                with pytest.raises(ValidationError, match="Template syntax error"):
                    await client._rest("POST", "/api/template")

    @pytest.mark.asyncio
    async def test_rest_api_error_message_extraction_text(self, client):
        """Test error message is extracted from plain text response."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Plain text error message"
        mock_response.json.side_effect = json.JSONDecodeError("msg", "doc", 0)

        with patch('httpx.AsyncClient') as mock_httpx:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_httpx.return_value = mock_client

            async with client:
                with pytest.raises(ValidationError, match="Plain text error message"):
                    await client._rest("POST", "/api/test")