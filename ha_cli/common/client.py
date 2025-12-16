"""Home Assistant API client with REST and WebSocket support."""

import asyncio
import contextlib
import json
import logging
import ssl
import time
from collections.abc import AsyncIterator, Callable
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from .exceptions import (
    AuthenticationError,
    ConnectionError,
    HAServerError,
    NotFoundError,
    TimeoutError,
    ValidationError,
    WebSocketError,
)

logger = logging.getLogger(__name__)

# Connection and timeout constants
WS_RECONNECT_BACKOFF = [1, 2, 4]  # Seconds between reconnection attempts
WS_HEARTBEAT_INTERVAL = 30  # Seconds between WebSocket heartbeat pings
WS_PING_TIMEOUT = 10  # Seconds to wait for pong response
WS_MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10MB max message size


def _extract_error_message(response: httpx.Response) -> str:
    """Extract error message from response body (JSON or text).

    Args:
        response: httpx Response object

    Returns:
        Error message string extracted from response body
    """
    try:
        body = response.json()
        fallback = response.text or f"HTTP {response.status_code}"
        result = body.get("message", body.get("error", fallback))
        return str(result)
    except (json.JSONDecodeError, ValueError):
        return response.text or f"HTTP {response.status_code}"


class HAClient:
    """Home Assistant client with REST and WebSocket support."""
    
    def __init__(
        self,
        url: str,
        token: str,
        timeout: int = 10,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize Home Assistant client.
        
        Args:
            url: Home Assistant URL (e.g., "http://homeassistant.local:8123")
            token: Long-lived access token
            timeout: Request timeout in seconds
            verify_ssl: Verify SSL certificates
        """
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        
        # Parse URL to get WebSocket URL
        parsed = urlparse(self.url)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        self.ws_url = f"{ws_scheme}://{parsed.netloc}/api/websocket"
        
        # HTTP client
        self._client: httpx.AsyncClient | None = None
        
        # WebSocket state
        self._ws: WebSocketClientProtocol | None = None
        self._ws_id = 0
        self._ws_lock = asyncio.Lock()
        self._ws_message_id = 1
        self._ws_subscriptions: dict[int, asyncio.Queue] = {}
        self._ws_listeners: dict[str, list[Callable]] = {}
        self._ws_reconnect_interval = 1  # Start with 1 second
        self._ws_max_reconnect_interval = 30  # Max 30 seconds
        self._ws_reconnect_task: asyncio.Task | None = None
        self._ws_heartbeat_task: asyncio.Task | None = None
        self._ws_last_heartbeat: float = 0
        self._ws_connected = asyncio.Event()
        
        # Headers for REST API
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
    
    async def __aenter__(self) -> "HAClient":
        """Enter async context."""
        self._client = httpx.AsyncClient(
            headers=self._headers,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        return self
    
    async def __aexit__(self, *args: Any) -> None:
        """Exit async context."""
        # Cancel background tasks
        if self._ws_heartbeat_task:
            self._ws_heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_heartbeat_task
        
        if self._ws_reconnect_task:
            self._ws_reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._ws_reconnect_task
        
        if self._client:
            await self._client.aclose()
        if self._ws:
            await self._ws.close()
    
    async def _rest(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> Any:
        """Make REST API request.

        Args:
            method: HTTP method
            endpoint: API endpoint
            json_data: Request body
            params: Query parameters
            expect_json: If True, parse response as JSON; if False, return raw text.
                        Defaults to True for backward compatibility.

        Returns:
            Response data (dict/list for JSON, str for text)

        Raises:
            Various exceptions based on status code
        """
        if not self._client:
            raise ConnectionError("Client not initialized. Use async context manager.")

        url = urljoin(self.url, endpoint)

        try:
            response = await self._client.request(
                method=method,
                url=url,
                json=json_data,
                params=params,
            )

            # Map status codes to exceptions with improved error message extraction
            if response.status_code == 401:
                raise AuthenticationError("Invalid or expired access token")
            elif response.status_code == 404:
                error_msg = _extract_error_message(response)
                http_fallback = f"HTTP {response.status_code}"
                msg = f"Resource not found: {endpoint}"
                if error_msg != http_fallback:
                    msg = f"{msg} - {error_msg}"
                raise NotFoundError(msg)
            elif response.status_code == 400:
                error_msg = _extract_error_message(response)
                raise ValidationError(f"Bad request: {error_msg}")
            elif response.status_code >= 500:
                error_msg = _extract_error_message(response)
                http_fallback = f"HTTP {response.status_code}"
                msg = f"Server error: {response.status_code}"
                if error_msg != http_fallback:
                    msg = f"{msg} - {error_msg}"
                raise HAServerError(msg)

            response.raise_for_status()

            # Return based on expect_json flag
            if not response.content:
                return None
            if expect_json:
                try:
                    return response.json()
                except (json.JSONDecodeError, ValueError) as e:
                    # Caller expected JSON but got something else
                    raise ValidationError(f"Expected JSON response, got: {response.text[:100]}") from e
            return response.text  # httpx property (not method)

        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request timed out: {e}") from e
        except httpx.ConnectError as e:
            raise ConnectionError(f"Failed to connect: {e}") from e


    async def _ensure_ws_connected(self) -> None:
        """Ensure WebSocket is connected and authenticated."""
        async with self._ws_lock:
            if self._ws and not self._ws.closed:
                return
            
            # Connect with retry logic
            retry_count = 0
            backoff = WS_RECONNECT_BACKOFF
            
            while retry_count < 3:
                try:
                    logger.debug(f"Connecting to WebSocket: {self.ws_url}")
                    self._ws = await websockets.connect(
                        self.ws_url,
                        ssl=self.verify_ssl if self.ws_url.startswith("wss") else None,
                        max_size=WS_MAX_MESSAGE_SIZE,
                    )
                    
                    # Wait for auth required message
                    msg = await self._ws.recv()
                    data = json.loads(msg)
                    
                    if data["type"] != "auth_required":
                        raise WebSocketError(f"Unexpected message type: {data['type']}")
                    
                    # Send auth
                    await self._ws.send(json.dumps({
                        "type": "auth",
                        "access_token": self.token,
                    }))
                    
                    # Wait for auth result
                    msg = await self._ws.recv()
                    data = json.loads(msg)
                    
                    if data["type"] == "auth_invalid":
                        raise AuthenticationError("Invalid access token")
                    elif data["type"] != "auth_ok":
                        raise WebSocketError(f"Auth failed: {data}")
                    
                    logger.debug("WebSocket connected and authenticated")
                    self._ws_id = 0
                    self._ws_connected.set()
                    
                    # Start heartbeat task
                    if self._ws_heartbeat_task:
                        self._ws_heartbeat_task.cancel()
                    self._ws_heartbeat_task = asyncio.create_task(self._ws_heartbeat())
                    
                    return
                    
                except (websockets.exceptions.WebSocketException, ConnectionError, ssl.SSLError, asyncio.TimeoutError) as e:
                    retry_count += 1
                    if retry_count >= 3:
                        raise WebSocketError(f"Failed to connect after 3 retries: {e}") from e
                    
                    wait_time = backoff[retry_count - 1]
                    logger.warning(f"WebSocket connection failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
    
    async def _ws_heartbeat(self) -> None:
        """Send periodic heartbeat to keep connection alive."""
        try:
            while self._ws and not self._ws.closed:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
                if self._ws and not self._ws.closed:
                    try:
                        pong_waiter = await self._ws.ping()
                        await asyncio.wait_for(pong_waiter, timeout=WS_PING_TIMEOUT)
                        self._ws_last_heartbeat = asyncio.get_running_loop().time()
                    except Exception as e:
                        logger.warning(f"WebSocket heartbeat failed: {e}")
                        # Trigger reconnection
                        await self._handle_ws_disconnect()
                        break
        except asyncio.CancelledError:
            pass
    
    async def _handle_ws_disconnect(self) -> None:
        """Handle WebSocket disconnection and trigger reconnection."""
        self._ws_connected.clear()
        
        # Cancel heartbeat
        if self._ws_heartbeat_task:
            self._ws_heartbeat_task.cancel()
        
        # Close the WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug(f"Error closing WebSocket during disconnect: {e}")
            self._ws = None
        
        # Start reconnection task if not already running
        if not self._ws_reconnect_task or self._ws_reconnect_task.done():
            self._ws_reconnect_task = asyncio.create_task(self._auto_reconnect())
    
    async def _auto_reconnect(self) -> None:
        """Automatically reconnect with exponential backoff."""
        reconnect_interval = self._ws_reconnect_interval
        
        while True:
            try:
                logger.info(f"Attempting WebSocket reconnection in {reconnect_interval}s...")
                await asyncio.sleep(reconnect_interval)
                
                await self._ensure_ws_connected()
                
                # Reset interval on successful connection
                self._ws_reconnect_interval = 1
                logger.info("WebSocket reconnected successfully")
                break
                
            except Exception as e:
                logger.error(f"WebSocket reconnection failed: {e}")
                # Exponential backoff
                reconnect_interval = min(
                    reconnect_interval * 2,
                    self._ws_max_reconnect_interval
                )
    
    async def wait_for_connection(self, timeout: float = 30) -> None:
        """Wait for WebSocket connection to be established.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Raises:
            TimeoutError: If connection not established within timeout
        """
        try:
            await asyncio.wait_for(self._ws_connected.wait(), timeout=timeout)
        except (TimeoutError, asyncio.TimeoutError) as e:
            raise TimeoutError(f"WebSocket connection not established within {timeout}s") from e
    
    async def _ws_call(
        self,
        msg_type: str,
        **kwargs: Any,
    ) -> Any:
        """Make WebSocket call.

        Args:
            msg_type: Message type
            **kwargs: Additional message fields
            
        Returns:
            Response data
            
        Raises:
            WebSocketError: On error
        """
        await self._ensure_ws_connected()
        
        if not self._ws:
            raise WebSocketError("WebSocket not connected")
        
        # Increment message ID
        self._ws_id += 1
        msg_id = self._ws_id
        
        # Build message
        message = {
            "id": msg_id,
            "type": msg_type,
            **kwargs,
        }
        
        # Send message
        await self._ws.send(json.dumps(message))
        
        # Wait for response
        try:
            while True:
                msg = await self._ws.recv()
                data = json.loads(msg)
                
                if data.get("id") == msg_id:
                    if data["type"] == "result":
                        if not data["success"]:
                            error = data.get("error", {})
                            raise WebSocketError(
                                f"{error.get('code', 'unknown')}: {error.get('message', 'Unknown error')}"
                            )
                        return data.get("result", {})
                    else:
                        raise WebSocketError(f"Unexpected response type: {data['type']}")
        except (ConnectionClosed, ConnectionClosedError) as e:
            logger.error(f"WebSocket connection lost during call: {e}")
            await self._handle_ws_disconnect()
            raise WebSocketError("Connection lost during WebSocket call") from e
    
    # Automation methods
    # Note: The REST API /api/config/automation/config requires the 'config'
    # integration to be enabled. We probe for availability and fall back gracefully.

    async def probe_automation_rest_api(self) -> bool:
        """Check if the automation REST API is available.

        The REST API requires the 'config' integration to be enabled in
        Home Assistant's configuration.yaml.

        Returns:
            True if REST API is available, False otherwise
        """
        try:
            # Try to fetch a known automation config via REST
            # We use a HEAD-like approach by trying to access the base config endpoint
            # This will 404 if config integration is not enabled
            await self._rest("GET", "/api/config/core/check_config")
            return True
        except NotFoundError:
            return False
        except Exception as e:
            logger.debug(f"REST API probe failed: {e}")
            return False

    async def get_automation_numeric_id(self, automation_id: str) -> str | None:
        """Get the numeric ID for an automation from its entity ID.

        The REST API uses numeric IDs (timestamps) while the WebSocket uses
        entity-based IDs. This method resolves the mapping.

        Args:
            automation_id: Automation ID (without 'automation.' prefix)

        Returns:
            Numeric ID string, or None if not found
        """
        try:
            # Get automation config via WebSocket - this includes the numeric ID
            entity_id = f"automation.{automation_id}" if not automation_id.startswith("automation.") else automation_id
            result = await self._ws_call("automation/config", entity_id=entity_id)

            # The config contains an 'id' field with the numeric ID
            if isinstance(result, dict):
                config = result.get("config", result)
                if isinstance(config, dict):
                    id_value = config.get("id")
                    return str(id_value) if id_value is not None else None
            return None
        except Exception as e:
            logger.debug(f"Failed to get numeric ID for {automation_id}: {e}")
            return None

    async def create_automation_rest(self, automation_config: dict[str, Any]) -> str:
        """Create a new automation via REST API.

        Args:
            automation_config: Automation configuration dictionary

        Returns:
            The numeric ID of the created automation

        Raises:
            NotFoundError: If REST API is not available (config integration disabled)
            ValidationError: If configuration is invalid
        """
        # Generate a numeric ID (timestamp-based, matching HA's pattern)
        numeric_id = str(int(time.time() * 1000))

        # Ensure the config has the ID set
        config = automation_config.copy()
        config["id"] = numeric_id

        endpoint = f"/api/config/automation/config/{numeric_id}"
        await self._rest("POST", endpoint, json_data=config)

        # Reload automations to apply the change
        await self.reload_automations()

        return numeric_id

    async def update_automation_rest(self, numeric_id: str, automation_config: dict[str, Any]) -> None:
        """Update an existing automation via REST API.

        Args:
            numeric_id: The numeric ID of the automation (not entity ID)
            automation_config: Updated automation configuration

        Raises:
            NotFoundError: If automation not found or REST API unavailable
            ValidationError: If configuration is invalid
        """
        # Ensure the config has the correct ID
        config = automation_config.copy()
        config["id"] = numeric_id

        endpoint = f"/api/config/automation/config/{numeric_id}"
        await self._rest("POST", endpoint, json_data=config)

        # Reload automations to apply the change
        await self.reload_automations()

    async def delete_automation_rest(self, numeric_id: str) -> None:
        """Delete an automation via REST API.

        Args:
            numeric_id: The numeric ID of the automation (not entity ID)

        Raises:
            NotFoundError: If automation not found or REST API unavailable
        """
        endpoint = f"/api/config/automation/config/{numeric_id}"
        await self._rest("DELETE", endpoint)

        # Reload automations to apply the change
        await self.reload_automations()

    async def get_automation_rest(self, numeric_id: str) -> dict[str, Any]:
        """Get automation configuration via REST API.

        Args:
            numeric_id: The numeric ID of the automation

        Returns:
            Automation configuration dictionary

        Raises:
            NotFoundError: If automation not found or REST API unavailable
        """
        endpoint = f"/api/config/automation/config/{numeric_id}"
        result = await self._rest("GET", endpoint)
        return dict(result) if isinstance(result, dict) else {}

    async def get_automation_states(self) -> list[dict[str, Any]]:
        """Get all automation entities via WebSocket.

        Returns:
            List of automation entity states
        """
        states = await self.get_states()
        return [s for s in states if s.get("entity_id", "").startswith("automation.")]

    async def get_automation(self, automation_id: str) -> dict[str, Any]:
        """Get automation configuration by ID via WebSocket.

        Args:
            automation_id: Automation ID (with or without 'automation.' prefix)

        Returns:
            Automation configuration dict

        Raises:
            NotFoundError: If automation not found
        """
        return await self.get_automation_config(automation_id)
    
    # WebSocket methods
    
    async def enable_automation(self, automation_id: str) -> None:
        """Enable automation via WebSocket."""
        await self._ws_call(
            "call_service",
            domain="automation",
            service="turn_on",
            service_data={"entity_id": f"automation.{automation_id}"},
        )
    
    async def disable_automation(self, automation_id: str) -> None:
        """Disable automation via WebSocket."""
        await self._ws_call(
            "call_service",
            domain="automation",
            service="turn_off",
            service_data={"entity_id": f"automation.{automation_id}"},
        )
    
    async def reload_automations(self) -> None:
        """Reload all automations via WebSocket."""
        await self._ws_call(
            "call_service",
            domain="automation",
            service="reload",
        )
    
    # Enhanced WebSocket methods for real-time features
    
    async def subscribe_events(
        self, 
        event_type: str | None = None,
        event_filter: Callable[[dict[str, Any]], bool] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to Home Assistant events.
        
        Args:
            event_type: Type of events to subscribe to (e.g., "state_changed")
            event_filter: Optional filter function for events
            
        Yields:
            Event data dictionaries
        """
        await self._ensure_ws_connected()
        
        if not self._ws:
            raise WebSocketError("WebSocket not connected")
        
        # Subscribe to events
        sub_id = self._ws_message_id
        self._ws_message_id += 1
        
        message = {
            "id": sub_id,
            "type": "subscribe_events",
        }
        if event_type:
            message["event_type"] = event_type
            
        await self._ws.send(json.dumps(message))
        
        # Wait for subscription confirmation
        while True:
            msg = await self._ws.recv()
            data = json.loads(msg)
            
            if data.get("id") == sub_id:
                if data["type"] == "result" and data["success"]:
                    break
                elif data["type"] == "result" and not data["success"]:
                    error = data.get("error", {})
                    raise WebSocketError(f"Subscription failed: {error}")
        
        # Yield events as they come
        try:
            while True:
                try:
                    msg = await self._ws.recv()
                    data = json.loads(msg)
                    
                    if data.get("id") == sub_id and data["type"] == "event":
                        event = data.get("event", {})
                        if event_filter is None or event_filter(event):
                            yield event
                except (ConnectionClosed, ConnectionClosedError) as e:
                    logger.error(f"WebSocket connection lost during event subscription: {e}")
                    await self._handle_ws_disconnect()
                    raise
        finally:
            # Unsubscribe when done
            if self._ws and not self._ws.closed:
                unsub_message = {
                    "id": self._ws_message_id,
                    "type": "unsubscribe_events",
                    "subscription": sub_id,
                }
                self._ws_message_id += 1
                try:
                    await self._ws.send(json.dumps(unsub_message))
                except Exception as e:
                    logger.debug(f"Error unsubscribing from events during cleanup: {e}")
    
    async def subscribe_automation_events(self) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to automation-related state changes.
        
        Yields:
            Automation state change events
        """
        def is_automation_event(event: dict[str, Any]) -> bool:
            """Filter for automation entities."""
            data = event.get("data", {})
            entity_id = data.get("entity_id", "") if isinstance(data, dict) else ""
            return bool(entity_id and isinstance(entity_id, str) and entity_id.startswith("automation."))
        
        async for event in self.subscribe_events("state_changed", is_automation_event):
            yield event
    
    async def subscribe_trigger(
        self,
        trigger_config: dict[str, Any]
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to a specific trigger for testing.
        
        Args:
            trigger_config: Trigger configuration to test
            
        Yields:
            Trigger events when the trigger fires
        """
        await self._ensure_ws_connected()
        
        if not self._ws:
            raise WebSocketError("WebSocket not connected")
        
        # Subscribe to trigger
        sub_id = self._ws_message_id
        self._ws_message_id += 1
        
        message = {
            "id": sub_id,
            "type": "subscribe_trigger",
            "trigger": trigger_config,
        }
        
        await self._ws.send(json.dumps(message))
        
        # Wait for subscription confirmation
        while True:
            msg = await self._ws.recv()
            data = json.loads(msg)
            
            if data.get("id") == sub_id:
                if data["type"] == "result" and data["success"]:
                    break
                elif data["type"] == "result" and not data["success"]:
                    error = data.get("error", {})
                    raise WebSocketError(f"Trigger subscription failed: {error}")
        
        # Yield trigger events
        try:
            while True:
                try:
                    msg = await self._ws.recv()
                    data = json.loads(msg)
                    
                    if data.get("id") == sub_id and data["type"] == "event":
                        yield data.get("event", {})
                except (ConnectionClosed, ConnectionClosedError) as e:
                    logger.error(f"WebSocket connection lost during trigger subscription: {e}")
                    await self._handle_ws_disconnect()
                    raise
        finally:
            # Unsubscribe when done
            if self._ws and not self._ws.closed:
                unsub_message = {
                    "id": self._ws_message_id,
                    "type": "unsubscribe_events",
                    "subscription": sub_id,
                }
                self._ws_message_id += 1
                try:
                    await self._ws.send(json.dumps(unsub_message))
                except Exception as e:
                    logger.debug(f"Error unsubscribing from state changes during cleanup: {e}")

    def _sanitize_value(self, value: Any) -> Any:
        """Recursively sanitize a value by removing control characters from strings."""
        import re
        
        if isinstance(value, str):
            # Remove ALL control characters including newlines, tabs, etc.
            return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', value)
        elif isinstance(value, dict):
            return {k: self._sanitize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._sanitize_value(item) for item in value]
        else:
            return value
    
    async def get_states(self) -> list[dict[str, Any]]:
        """Get all entity states via WebSocket.
        
        Returns:
            List of all entity states with sanitized strings
        """
        await self._ensure_ws_connected()
        
        if not self._ws:
            raise WebSocketError("WebSocket not connected")
        
        # Increase message size limit for large responses
        if hasattr(self._ws, 'max_size'):
            self._ws.max_size = 10 * 1024 * 1024  # 10MB
        
        result = await self._ws_call("get_states")
        
        if isinstance(result, list):
            return result
        return []

    async def call_automation_service(
        self,
        service: str,
        entity_ids: list[str] | str,
        service_data: dict[str, Any] | None = None
    ) -> None:
        """Call an automation service via WebSocket.
        
        Args:
            service: Service name (turn_on, turn_off, trigger, toggle)
            entity_ids: Entity ID(s) to target
            service_data: Optional service data
        """
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        
        data = service_data or {}
        data["entity_id"] = entity_ids
        
        await self._ws_call(
            "call_service",
            domain="automation",
            service=service,
            service_data=data,
        )
    
    async def get_automation_config(self, automation_id: str) -> dict[str, Any]:
        """Get automation configuration via WebSocket.

        Args:
            automation_id: ID of automation to get (without 'automation.' prefix)

        Returns:
            Automation configuration

        Raises:
            NotFoundError: If automation not found
        """
        # The WebSocket API expects entity_id format
        entity_id = f"automation.{automation_id}" if not automation_id.startswith("automation.") else automation_id

        try:
            result = await self._ws_call(
                "automation/config",
                entity_id=entity_id,
            )
            # The result contains a 'config' key with the actual configuration
            if isinstance(result, dict) and "config" in result:
                config = result["config"]
                # Add the ID to the config if not present
                if isinstance(config, dict) and "id" not in config:
                    config["id"] = automation_id.replace("automation.", "")
                return dict(config) if isinstance(config, dict) else {}
            return dict(result) if isinstance(result, dict) else {}
        except WebSocketError as e:
            if "not_found" in str(e).lower():
                raise NotFoundError(f"Automation not found: {automation_id}") from e
            raise

    # Dashboard WebSocket methods
    
    async def list_dashboards(self) -> list[dict[str, Any]]:
        """List all Lovelace dashboards via WebSocket.
        
        Returns:
            List of dashboard info
        """
        result = await self._ws_call("lovelace/dashboards/list")
        return result if isinstance(result, list) else []
    
    async def get_dashboard_config(self, url_path: str | None = None) -> dict[str, Any]:
        """Get dashboard configuration via WebSocket.
        
        Args:
            url_path: Dashboard URL path (None for default dashboard)
            
        Returns:
            Dashboard configuration
            
        Raises:
            NotFoundError: If dashboard not found
        """
        try:
            if url_path:
                result = await self._ws_call(
                    "lovelace/config",
                    url_path=url_path,
                )
            else:
                # Default dashboard
                result = await self._ws_call("lovelace/config")

            return result if isinstance(result, dict) else {}
        except WebSocketError as e:
            if "not_found" in str(e).lower():
                raise NotFoundError(f"Dashboard not found: {url_path or 'default'}") from e
            raise

    async def save_dashboard_config(
        self, 
        config: dict[str, Any], 
        url_path: str | None = None
    ) -> None:
        """Save dashboard configuration via WebSocket.
        
        Args:
            config: Dashboard configuration to save
            url_path: Dashboard URL path (None for default dashboard)
            
        Raises:
            ValidationError: If configuration is invalid
            NotFoundError: If dashboard not found (for non-default dashboards)
        """
        try:
            if url_path:
                await self._ws_call(
                    "lovelace/config/save",
                    url_path=url_path,
                    config=config,
                )
            else:
                # Default dashboard
                await self._ws_call(
                    "lovelace/config/save",
                    config=config,
                )
        except WebSocketError as e:
            error_msg = str(e).lower()
            if "not_found" in error_msg:
                raise NotFoundError(f"Dashboard not found: {url_path or 'default'}") from e
            elif "invalid" in error_msg or "validation" in error_msg:
                raise ValidationError(f"Invalid dashboard configuration: {e}") from e
            raise

    async def delete_dashboard(self, dashboard_id: str) -> None:
        """Delete a dashboard via WebSocket.
        
        Args:
            dashboard_id: Dashboard ID to delete
            
        Raises:
            NotFoundError: If dashboard not found
            ValidationError: If trying to delete default dashboard
        """
        try:
            await self._ws_call(
                "lovelace/dashboards/delete",
                dashboard_id=dashboard_id,
            )
        except WebSocketError as e:
            error_msg = str(e).lower()
            if "not_found" in error_msg:
                raise NotFoundError(f"Dashboard not found: {dashboard_id}") from e
            elif "default" in error_msg:
                raise ValidationError("Cannot delete the default dashboard") from e
            raise

    async def create_dashboard(
        self,
        dashboard_id: str,
        url_path: str,
        title: str,
        icon: str | None = None,
        show_in_sidebar: bool = True,
        require_admin: bool = False,
    ) -> None:
        """Create a new dashboard via WebSocket.
        
        Args:
            dashboard_id: Unique dashboard ID
            url_path: URL path for the dashboard
            title: Dashboard title
            icon: Optional icon (e.g., "mdi:view-dashboard")
            show_in_sidebar: Whether to show in sidebar
            require_admin: Whether admin access is required
            
        Raises:
            ValidationError: If dashboard already exists or invalid parameters
        """
        try:
            config = {
                "id": dashboard_id,
                "url_path": url_path,
                "title": title,
                "show_in_sidebar": show_in_sidebar,
                "require_admin": require_admin,
            }
            
            if icon:
                config["icon"] = icon
            
            await self._ws_call(
                "lovelace/dashboards/create",
                **config,
            )
        except WebSocketError as e:
            error_msg = str(e).lower()
            if "already exists" in error_msg or "duplicate" in error_msg:
                raise ValidationError(f"Dashboard already exists: {dashboard_id}") from e
            elif "invalid" in error_msg:
                raise ValidationError(f"Invalid dashboard parameters: {e}") from e
            raise

    async def update_dashboard(
        self,
        dashboard_id: str,
        url_path: str | None = None,
        title: str | None = None,
        icon: str | None = None,
        show_in_sidebar: bool | None = None,
        require_admin: bool | None = None,
    ) -> None:
        """Update dashboard settings via WebSocket.
        
        Args:
            dashboard_id: Dashboard ID to update
            url_path: New URL path (optional)
            title: New title (optional)
            icon: New icon (optional)
            show_in_sidebar: New sidebar visibility (optional)
            require_admin: New admin requirement (optional)
            
        Raises:
            NotFoundError: If dashboard not found
            ValidationError: If invalid parameters
        """
        try:
            update_data: dict[str, Any] = {"dashboard_id": dashboard_id}

            if url_path is not None:
                update_data["url_path"] = url_path
            if title is not None:
                update_data["title"] = title
            if icon is not None:
                update_data["icon"] = icon
            if show_in_sidebar is not None:
                update_data["show_in_sidebar"] = show_in_sidebar
            if require_admin is not None:
                update_data["require_admin"] = require_admin
            
            await self._ws_call(
                "lovelace/dashboards/update",
                **update_data,
            )
        except WebSocketError as e:
            error_msg = str(e).lower()
            if "not_found" in error_msg:
                raise NotFoundError(f"Dashboard not found: {dashboard_id}") from e
            elif "invalid" in error_msg:
                raise ValidationError(f"Invalid dashboard parameters: {e}") from e
            raise