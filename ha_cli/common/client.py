"""Home Assistant API client with REST and WebSocket support."""

import asyncio
import json
import logging
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
            try:
                await self._ws_heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._ws_reconnect_task:
            self._ws_reconnect_task.cancel()
            try:
                await self._ws_reconnect_task
            except asyncio.CancelledError:
                pass
        
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
    ) -> Any:
        """Make REST API request.
        
        Args:
            method: HTTP method
            endpoint: API endpoint
            json_data: Request body
            params: Query parameters
            
        Returns:
            Response data
            
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
            
            # Map status codes to exceptions
            if response.status_code == 401:
                raise AuthenticationError("Invalid or expired access token")
            elif response.status_code == 404:
                raise NotFoundError(f"Resource not found: {endpoint}")
            elif response.status_code == 400:
                raise ValidationError(f"Bad request: {response.text}")
            elif response.status_code >= 500:
                raise HAServerError(f"Server error: {response.status_code}")
            
            response.raise_for_status()
            
            # Return JSON if available
            if response.content:
                return response.json()
            return None
            
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request timed out: {e}")
        except httpx.ConnectError as e:
            raise ConnectionError(f"Failed to connect: {e}")
    
    async def _ensure_ws_connected(self) -> None:
        """Ensure WebSocket is connected and authenticated."""
        async with self._ws_lock:
            if self._ws and not self._ws.closed:
                return
            
            # Connect with retry logic
            retry_count = 0
            backoff = [1, 2, 4]  # seconds
            
            while retry_count < 3:
                try:
                    logger.debug(f"Connecting to WebSocket: {self.ws_url}")
                    self._ws = await websockets.connect(
                        self.ws_url,
                        ssl=self.verify_ssl if self.ws_url.startswith("wss") else None,
                        max_size=10 * 1024 * 1024,  # 10MB for large responses
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
                    
                except (websockets.exceptions.WebSocketException, ConnectionError) as e:
                    retry_count += 1
                    if retry_count >= 3:
                        raise WebSocketError(f"Failed to connect after 3 retries: {e}")
                    
                    wait_time = backoff[retry_count - 1]
                    logger.warning(f"WebSocket connection failed, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
    
    async def _ws_heartbeat(self) -> None:
        """Send periodic heartbeat to keep connection alive."""
        try:
            while self._ws and not self._ws.closed:
                # Send ping every 30 seconds
                await asyncio.sleep(30)
                if self._ws and not self._ws.closed:
                    try:
                        pong_waiter = await self._ws.ping()
                        await asyncio.wait_for(pong_waiter, timeout=10)
                        self._ws_last_heartbeat = asyncio.get_event_loop().time()
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
        except asyncio.TimeoutError:
            raise TimeoutError(f"WebSocket connection not established within {timeout}s")
    
    async def _ws_call(
        self,
        msg_type: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
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
            raise WebSocketError("Connection lost during WebSocket call")
    
    # REST API methods
    
    async def list_automations(self) -> list[dict[str, Any]]:
        """List all automations via REST API."""
        return await self._rest("GET", "/api/config/automation/config")
    
    async def get_automation_states(self) -> list[dict[str, Any]]:
        """Get all automation entities via WebSocket.
        
        Returns:
            List of automation entity states
        """
        states = await self.get_states()
        return [s for s in states if s.get("entity_id", "").startswith("automation.")]
    
    async def create_automation(self, automation: dict[str, Any]) -> dict[str, Any]:
        """Create new automation via REST API."""
        result = await self._rest("POST", "/api/config/automation/config", json_data=automation)
        # Reload after create
        await self.reload_automations()
        return result
    
    async def get_automation(self, automation_id: str) -> dict[str, Any]:
        """Get automation by ID via REST API."""
        return await self._rest("GET", f"/api/config/automation/config/{automation_id}")
    
    async def update_automation(self, automation_id: str, automation: dict[str, Any]) -> dict[str, Any]:
        """Update automation via REST API."""
        result = await self._rest("POST", f"/api/config/automation/config/{automation_id}", json_data=automation)
        # Reload after update
        await self.reload_automations()
        return result
    
    async def delete_automation(self, automation_id: str) -> None:
        """Delete automation via REST API."""
        await self._rest("DELETE", f"/api/config/automation/config/{automation_id}")
        # Reload after delete
        await self.reload_automations()
    
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
            entity_id = event.get("data", {}).get("entity_id", "")
            return entity_id.startswith("automation.")
        
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
            cleaned = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', value)
            return cleaned
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
    
    async def get_automation_states(self) -> list[dict[str, Any]]:
        """Get all automation entity states.
        
        Returns:
            List of automation states
        """
        all_states = await self.get_states()
        return [
            state for state in all_states 
            if state.get("entity_id", "").startswith("automation.")
        ]
    
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
            automation_id: ID of automation to get
            
        Returns:
            Automation configuration
            
        Raises:
            NotFoundError: If automation not found
        """
        try:
            result = await self._ws_call(
                "automation/config",
                automation_id=automation_id,
            )
            return result
        except WebSocketError as e:
            if "not_found" in str(e).lower():
                raise NotFoundError(f"Automation not found: {automation_id}")
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
            
            return result
        except WebSocketError as e:
            if "not_found" in str(e).lower():
                raise NotFoundError(f"Dashboard not found: {url_path or 'default'}")
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
                raise NotFoundError(f"Dashboard not found: {url_path or 'default'}")
            elif "invalid" in error_msg or "validation" in error_msg:
                raise ValidationError(f"Invalid dashboard configuration: {e}")
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
                raise NotFoundError(f"Dashboard not found: {dashboard_id}")
            elif "default" in error_msg:
                raise ValidationError("Cannot delete the default dashboard")
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
                raise ValidationError(f"Dashboard already exists: {dashboard_id}")
            elif "invalid" in error_msg:
                raise ValidationError(f"Invalid dashboard parameters: {e}")
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
            update_data = {"dashboard_id": dashboard_id}
            
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
                raise NotFoundError(f"Dashboard not found: {dashboard_id}")
            elif "invalid" in error_msg:
                raise ValidationError(f"Invalid dashboard parameters: {e}")
            raise