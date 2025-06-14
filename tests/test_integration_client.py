"""Integration tests for HAClient."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import httpx
import websockets

from ha_automation.client import HAClient
from ha_automation.exceptions import (
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
        from ha_automation.exceptions import TimeoutError
        
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
        
        mock_ws.recv.side_effect = [auth_required, auth_ok, result_response]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            async with client:
                result = await client._ws_call("call_service", domain="test", service="test")
                
                assert result == {"test": "success"}
    
    @pytest.mark.asyncio
    async def test_websocket_call_error(self, client):
        """Test WebSocket service call error."""
        mock_ws = AsyncMock()
        
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
        
        mock_ws.recv.side_effect = [auth_required, auth_ok, error_response]
        
        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_ws):
            async with client:
                with pytest.raises(WebSocketError, match="test_error: Test error message"):
                    await client._ws_call("call_service", domain="test", service="test")
    
    @pytest.mark.asyncio
    async def test_list_automations(self, client):
        """Test list_automations method."""
        expected_data = [
            {"id": "test1", "alias": "Test 1"},
            {"id": "test2", "alias": "Test 2"}
        ]
        
        with patch.object(client, '_rest', return_value=expected_data) as mock_rest:
            async with client:
                result = await client.list_automations()
                
                assert result == expected_data
                mock_rest.assert_called_once_with("GET", "/api/config/automation/config")
    
    @pytest.mark.asyncio
    async def test_create_automation(self, client):
        """Test create_automation method."""
        automation_data = {"alias": "Test", "trigger": [], "action": []}
        expected_result = {"id": "new_automation"}
        
        with patch.object(client, '_rest', return_value=expected_result) as mock_rest, \
             patch.object(client, 'reload_automations') as mock_reload:
            
            async with client:
                result = await client.create_automation(automation_data)
                
                assert result == expected_result
                mock_rest.assert_called_once_with(
                    "POST", 
                    "/api/config/automation/config", 
                    json_data=automation_data
                )
                mock_reload.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_automation(self, client):
        """Test get_automation method."""
        automation_id = "test_automation"
        expected_data = {"id": automation_id, "alias": "Test"}
        
        with patch.object(client, '_rest', return_value=expected_data) as mock_rest:
            async with client:
                result = await client.get_automation(automation_id)
                
                assert result == expected_data
                mock_rest.assert_called_once_with("GET", f"/api/config/automation/config/{automation_id}")
    
    @pytest.mark.asyncio
    async def test_update_automation(self, client):
        """Test update_automation method."""
        automation_id = "test_automation"
        automation_data = {"alias": "Updated Test", "trigger": [], "action": []}
        expected_result = {"id": automation_id}
        
        with patch.object(client, '_rest', return_value=expected_result) as mock_rest, \
             patch.object(client, 'reload_automations') as mock_reload:
            
            async with client:
                result = await client.update_automation(automation_id, automation_data)
                
                assert result == expected_result
                mock_rest.assert_called_once_with(
                    "POST", 
                    f"/api/config/automation/config/{automation_id}", 
                    json_data=automation_data
                )
                mock_reload.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_delete_automation(self, client):
        """Test delete_automation method."""
        automation_id = "test_automation"
        
        with patch.object(client, '_rest', return_value=None) as mock_rest, \
             patch.object(client, 'reload_automations') as mock_reload:
            
            async with client:
                await client.delete_automation(automation_id)
                
                mock_rest.assert_called_once_with("DELETE", f"/api/config/automation/config/{automation_id}")
                mock_reload.assert_called_once()
    
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