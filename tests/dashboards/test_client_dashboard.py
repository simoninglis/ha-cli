"""Tests for HAClient dashboard WebSocket methods."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

from ha_cli.common.client import HAClient
from ha_cli.common.exceptions import NotFoundError, ValidationError, WebSocketError


class TestHAClientDashboardMethods:
    """Test HAClient dashboard WebSocket methods."""

    @pytest.fixture
    async def client(self):
        """Create test client."""
        client = HAClient("http://test:8123", "test-token")
        yield client
        # Cleanup tasks
        if hasattr(client, '_ws_reader_task') and client._ws_reader_task:
            client._ws_reader_task.cancel()
            try:
                await client._ws_reader_task
            except (asyncio.CancelledError, Exception):
                pass
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

    @pytest.fixture
    def auth_responses(self):
        """Standard authentication responses."""
        return [
            json.dumps({"type": "auth_required", "ha_version": "2025.6.0"}),
            json.dumps({"type": "auth_ok", "ha_version": "2025.6.0"}),
        ]

    @pytest.fixture
    def ws_terminator(self):
        """Terminator for WebSocket reader task graceful exit."""
        return ConnectionClosedError(None, None)


class TestListDashboards(TestHAClientDashboardMethods):
    """Tests for list_dashboards() method."""

    @pytest.mark.asyncio
    async def test_list_dashboards_success(self, client, mock_websocket, auth_responses):
        """Test listing dashboards successfully."""
        dashboards_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": [
                {
                    "id": "mobile",
                    "url_path": "mobile",
                    "title": "Mobile Dashboard",
                    "icon": "mdi:cellphone",
                    "require_admin": False,
                    "show_in_sidebar": True,
                    "mode": "storage",
                },
                {
                    "id": "tablet",
                    "url_path": "tablet",
                    "title": "Tablet Dashboard",
                    "icon": "mdi:tablet",
                    "require_admin": True,
                    "show_in_sidebar": False,
                    "mode": "yaml",
                },
            ]
        })

        mock_websocket.recv.side_effect = auth_responses + [dashboards_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                dashboards = await client.list_dashboards()

                assert len(dashboards) == 2
                assert dashboards[0]["id"] == "mobile"
                assert dashboards[0]["title"] == "Mobile Dashboard"
                assert dashboards[1]["id"] == "tablet"
                assert dashboards[1]["mode"] == "yaml"

    @pytest.mark.asyncio
    async def test_list_dashboards_empty(self, client, mock_websocket, auth_responses):
        """Test listing dashboards when none exist."""
        empty_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": []
        })

        mock_websocket.recv.side_effect = auth_responses + [empty_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                dashboards = await client.list_dashboards()

                assert dashboards == []

    @pytest.mark.asyncio
    async def test_list_dashboards_non_list_result(self, client, mock_websocket, auth_responses):
        """Test list_dashboards handles non-list result gracefully."""
        invalid_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None  # Sometimes HA returns null instead of empty list
        })

        mock_websocket.recv.side_effect = auth_responses + [invalid_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                dashboards = await client.list_dashboards()

                # Should return empty list, not None
                assert dashboards == []


class TestGetDashboardConfig(TestHAClientDashboardMethods):
    """Tests for get_dashboard_config() method."""

    @pytest.mark.asyncio
    async def test_get_dashboard_config_success(self, client, mock_websocket, auth_responses):
        """Test getting dashboard config successfully."""
        config_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": {
                "title": "Mobile Dashboard",
                "views": [
                    {
                        "title": "Home",
                        "path": "home",
                        "cards": [
                            {"type": "entities", "entities": ["light.living_room"]}
                        ]
                    }
                ]
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [config_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                config = await client.get_dashboard_config("mobile")

                assert config["title"] == "Mobile Dashboard"
                assert len(config["views"]) == 1
                assert config["views"][0]["title"] == "Home"

    @pytest.mark.asyncio
    async def test_get_dashboard_config_default(self, client, mock_websocket, auth_responses):
        """Test getting default dashboard config (url_path=None)."""
        config_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": {
                "title": "Default Dashboard",
                "views": []
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [config_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                config = await client.get_dashboard_config(None)

                assert config["title"] == "Default Dashboard"

                # Verify the call was made without url_path
                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["type"] == "lovelace/config"
                assert "url_path" not in msg

    @pytest.mark.asyncio
    async def test_get_dashboard_config_not_found(self, client, mock_websocket, auth_responses):
        """Test getting config for non-existent dashboard."""
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "not_found",
                "message": "Dashboard not found"
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(NotFoundError, match="Dashboard not found"):
                    await client.get_dashboard_config("nonexistent")

    @pytest.mark.asyncio
    async def test_get_dashboard_config_empty_result(self, client, mock_websocket, auth_responses):
        """Test get_dashboard_config handles empty result gracefully."""
        empty_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None  # Sometimes HA returns null
        })

        mock_websocket.recv.side_effect = auth_responses + [empty_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                config = await client.get_dashboard_config("mobile")

                # Should return empty dict, not None
                assert config == {}


class TestSaveDashboardConfig(TestHAClientDashboardMethods):
    """Tests for save_dashboard_config() method."""

    @pytest.mark.asyncio
    async def test_save_dashboard_config_success(self, client, mock_websocket, auth_responses):
        """Test saving dashboard config successfully."""
        save_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })

        mock_websocket.recv.side_effect = auth_responses + [save_response, ConnectionClosedError(None, None)]

        config = {
            "title": "Updated Dashboard",
            "views": [{"title": "Home", "cards": []}]
        }

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                # Should not raise
                await client.save_dashboard_config(config, "mobile")

                # Verify the call
                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["type"] == "lovelace/config/save"
                assert msg["url_path"] == "mobile"
                assert msg["config"]["title"] == "Updated Dashboard"

    @pytest.mark.asyncio
    async def test_save_dashboard_config_default(self, client, mock_websocket, auth_responses):
        """Test saving config to default dashboard."""
        save_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })

        mock_websocket.recv.side_effect = auth_responses + [save_response, ConnectionClosedError(None, None)]

        config = {"title": "Default", "views": []}

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                await client.save_dashboard_config(config, None)

                # Verify the call was made without url_path
                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["type"] == "lovelace/config/save"
                assert "url_path" not in msg

    @pytest.mark.asyncio
    async def test_save_dashboard_config_not_found(self, client, mock_websocket, auth_responses):
        """Test saving config to non-existent dashboard."""
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "not_found",
                "message": "Dashboard not found"
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(NotFoundError, match="Dashboard not found"):
                    await client.save_dashboard_config({}, "nonexistent")

    @pytest.mark.asyncio
    async def test_save_dashboard_config_validation_error(self, client, mock_websocket, auth_responses):
        """Test saving invalid dashboard config."""
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "invalid_config",
                "message": "Invalid configuration format"
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(ValidationError, match="Invalid dashboard configuration"):
                    await client.save_dashboard_config({"bad": "config"}, "mobile")


class TestDeleteDashboard(TestHAClientDashboardMethods):
    """Tests for delete_dashboard() method."""

    @pytest.mark.asyncio
    async def test_delete_dashboard_success(self, client, mock_websocket, auth_responses):
        """Test deleting dashboard successfully."""
        delete_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })

        mock_websocket.recv.side_effect = auth_responses + [delete_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                # Should not raise
                await client.delete_dashboard("mobile")

                # Verify the call
                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["type"] == "lovelace/dashboards/delete"
                assert msg["dashboard_id"] == "mobile"

    @pytest.mark.asyncio
    async def test_delete_dashboard_not_found(self, client, mock_websocket, auth_responses):
        """Test deleting non-existent dashboard."""
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "not_found",
                "message": "Dashboard not found"
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(NotFoundError, match="Dashboard not found"):
                    await client.delete_dashboard("nonexistent")

    @pytest.mark.asyncio
    async def test_delete_dashboard_default_protected(self, client, mock_websocket, auth_responses):
        """Test that deleting default dashboard raises ValidationError."""
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "invalid",
                "message": "Cannot delete the default dashboard"
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(ValidationError, match="Cannot delete the default dashboard"):
                    await client.delete_dashboard("default")


class TestCreateDashboard(TestHAClientDashboardMethods):
    """Tests for create_dashboard() method."""

    @pytest.mark.asyncio
    async def test_create_dashboard_success(self, client, mock_websocket, auth_responses):
        """Test creating dashboard successfully."""
        create_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })

        mock_websocket.recv.side_effect = auth_responses + [create_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                await client.create_dashboard(
                    dashboard_id="new-dash",
                    url_path="new-dashboard",
                    title="New Dashboard",
                    icon="mdi:view-dashboard",
                    show_in_sidebar=True,
                    require_admin=False,
                )

                # Verify the call
                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["type"] == "lovelace/dashboards/create"
                assert msg["id"] == "new-dash"
                assert msg["url_path"] == "new-dashboard"
                assert msg["title"] == "New Dashboard"
                assert msg["icon"] == "mdi:view-dashboard"
                assert msg["show_in_sidebar"] is True
                assert msg["require_admin"] is False

    @pytest.mark.asyncio
    async def test_create_dashboard_minimal(self, client, mock_websocket, auth_responses):
        """Test creating dashboard with minimal parameters."""
        create_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })

        mock_websocket.recv.side_effect = auth_responses + [create_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                await client.create_dashboard(
                    dashboard_id="simple",
                    url_path="simple",
                    title="Simple Dashboard",
                )

                # Verify the call has defaults
                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["show_in_sidebar"] is True  # default
                assert msg["require_admin"] is False  # default
                assert "icon" not in msg  # not provided

    @pytest.mark.asyncio
    async def test_create_dashboard_duplicate(self, client, mock_websocket, auth_responses):
        """Test creating dashboard with existing ID."""
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "already_exists",
                "message": "Dashboard already exists with id: existing"
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(ValidationError, match="Dashboard already exists"):
                    await client.create_dashboard(
                        dashboard_id="existing",
                        url_path="existing",
                        title="Existing",
                    )

    @pytest.mark.asyncio
    async def test_create_dashboard_invalid_params(self, client, mock_websocket, auth_responses):
        """Test creating dashboard with invalid parameters."""
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "invalid",
                "message": "Invalid url_path format"
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(ValidationError, match="Invalid dashboard parameters"):
                    await client.create_dashboard(
                        dashboard_id="bad",
                        url_path="bad path with spaces",
                        title="Bad",
                    )


class TestUpdateDashboard(TestHAClientDashboardMethods):
    """Tests for update_dashboard() method."""

    @pytest.mark.asyncio
    async def test_update_dashboard_success(self, client, mock_websocket, auth_responses):
        """Test updating dashboard successfully."""
        update_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })

        mock_websocket.recv.side_effect = auth_responses + [update_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                await client.update_dashboard(
                    dashboard_id="mobile",
                    title="Updated Mobile",
                    icon="mdi:phone",
                    show_in_sidebar=False,
                )

                # Verify the call
                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["type"] == "lovelace/dashboards/update"
                assert msg["dashboard_id"] == "mobile"
                assert msg["title"] == "Updated Mobile"
                assert msg["icon"] == "mdi:phone"
                assert msg["show_in_sidebar"] is False

    @pytest.mark.asyncio
    async def test_update_dashboard_partial(self, client, mock_websocket, auth_responses):
        """Test updating dashboard with partial parameters."""
        update_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })

        mock_websocket.recv.side_effect = auth_responses + [update_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                # Only update title
                await client.update_dashboard(
                    dashboard_id="mobile",
                    title="New Title Only",
                )

                # Verify only dashboard_id and title are sent
                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["dashboard_id"] == "mobile"
                assert msg["title"] == "New Title Only"
                # These should not be in the message since they weren't specified
                assert "url_path" not in msg
                assert "icon" not in msg
                assert "show_in_sidebar" not in msg
                assert "require_admin" not in msg

    @pytest.mark.asyncio
    async def test_update_dashboard_not_found(self, client, mock_websocket, auth_responses):
        """Test updating non-existent dashboard."""
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "not_found",
                "message": "Dashboard not found"
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(NotFoundError, match="Dashboard not found"):
                    await client.update_dashboard(
                        dashboard_id="nonexistent",
                        title="Update",
                    )

    @pytest.mark.asyncio
    async def test_update_dashboard_invalid_params(self, client, mock_websocket, auth_responses):
        """Test updating dashboard with invalid parameters."""
        error_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": False,
            "error": {
                "code": "invalid",
                "message": "Invalid icon format"
            }
        })

        mock_websocket.recv.side_effect = auth_responses + [error_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                with pytest.raises(ValidationError, match="Invalid dashboard parameters"):
                    await client.update_dashboard(
                        dashboard_id="mobile",
                        icon="not-a-valid-icon",
                    )

    @pytest.mark.asyncio
    async def test_update_dashboard_url_path(self, client, mock_websocket, auth_responses):
        """Test updating dashboard URL path."""
        update_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })

        mock_websocket.recv.side_effect = auth_responses + [update_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                await client.update_dashboard(
                    dashboard_id="mobile",
                    url_path="new-mobile-path",
                )

                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["url_path"] == "new-mobile-path"

    @pytest.mark.asyncio
    async def test_update_dashboard_require_admin(self, client, mock_websocket, auth_responses):
        """Test updating dashboard admin requirement."""
        update_response = json.dumps({
            "id": 1,
            "type": "result",
            "success": True,
            "result": None
        })

        mock_websocket.recv.side_effect = auth_responses + [update_response, ConnectionClosedError(None, None)]

        with patch('websockets.connect', new_callable=AsyncMock, return_value=mock_websocket):
            async with client:
                await client.update_dashboard(
                    dashboard_id="admin-panel",
                    require_admin=True,
                )

                call_args = mock_websocket.send.call_args_list[-1]
                msg = json.loads(call_args[0][0])
                assert msg["require_admin"] is True
