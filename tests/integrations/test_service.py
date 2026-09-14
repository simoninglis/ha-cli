"""Tests for integrations service layer."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ha_cli.common.exceptions import NotFoundError, ValidationError, WebSocketError
from ha_cli.domains.integrations.service import IntegrationService


@pytest.fixture()
def mock_client() -> MagicMock:
    """Create a mock HAClient."""
    client = MagicMock()
    client._ws_call = AsyncMock()
    client._rest = AsyncMock()
    return client


class TestListEntries:
    """Tests for IntegrationService.list_entries."""

    @pytest.mark.asyncio()
    async def test_list_entries_success(self, mock_client: MagicMock) -> None:
        """Test listing entries successfully."""
        mock_client._ws_call.return_value = [
            {
                "entry_id": "abc123",
                "domain": "media_extractor",
                "title": "Media extractor",
                "state": "loaded",
                "source": "user",
            }
        ]

        service = IntegrationService(mock_client)
        entries = await service.list_entries()

        assert len(entries) == 1
        assert entries[0].domain == "media_extractor"
        assert entries[0].entry_id == "abc123"

    @pytest.mark.asyncio()
    async def test_list_entries_empty(self, mock_client: MagicMock) -> None:
        """Test listing entries when none exist."""
        mock_client._ws_call.return_value = []

        service = IntegrationService(mock_client)
        entries = await service.list_entries()

        assert len(entries) == 0

    @pytest.mark.asyncio()
    async def test_list_entries_filter_domain(self, mock_client: MagicMock) -> None:
        """Test filtering entries by domain."""
        mock_client._ws_call.return_value = [
            {"entry_id": "1", "domain": "esphome", "title": "ESP1", "state": "loaded", "source": "user"},
            {"entry_id": "2", "domain": "media_extractor", "title": "Media", "state": "loaded", "source": "user"},
            {"entry_id": "3", "domain": "esphome", "title": "ESP2", "state": "loaded", "source": "user"},
        ]

        service = IntegrationService(mock_client)
        entries = await service.list_entries(domain="esphome")

        assert len(entries) == 2
        assert all(e.domain == "esphome" for e in entries)

    @pytest.mark.asyncio()
    async def test_list_entries_filter_state(self, mock_client: MagicMock) -> None:
        """Test filtering entries by state."""
        mock_client._ws_call.return_value = [
            {"entry_id": "1", "domain": "test", "title": "T1", "state": "loaded", "source": "user"},
            {"entry_id": "2", "domain": "test", "title": "T2", "state": "setup_error", "source": "user"},
        ]

        service = IntegrationService(mock_client)
        entries = await service.list_entries(state="setup_error")

        assert len(entries) == 1
        assert entries[0].state == "setup_error"

    @pytest.mark.asyncio()
    async def test_list_entries_sorting(self, mock_client: MagicMock) -> None:
        """Test that entries are sorted by domain then title."""
        mock_client._ws_call.return_value = [
            {"entry_id": "1", "domain": "zwave", "title": "Z", "state": "loaded", "source": "user"},
            {"entry_id": "2", "domain": "esphome", "title": "B", "state": "loaded", "source": "user"},
            {"entry_id": "3", "domain": "esphome", "title": "A", "state": "loaded", "source": "user"},
        ]

        service = IntegrationService(mock_client)
        entries = await service.list_entries()

        assert entries[0].domain == "esphome"
        assert entries[0].title == "A"
        assert entries[1].domain == "esphome"
        assert entries[1].title == "B"
        assert entries[2].domain == "zwave"


class TestGetEntry:
    """Tests for IntegrationService.get_entry."""

    @pytest.mark.asyncio()
    async def test_get_entry_success(self, mock_client: MagicMock) -> None:
        """Test getting entry by ID."""
        mock_client._ws_call.return_value = {
            "config_entry": {
                "entry_id": "abc123",
                "domain": "test",
                "title": "Test",
                "state": "loaded",
                "source": "user",
            }
        }

        service = IntegrationService(mock_client)
        entry = await service.get_entry("abc123")

        assert entry is not None
        assert entry.entry_id == "abc123"

    @pytest.mark.asyncio()
    async def test_get_entry_not_found(self, mock_client: MagicMock) -> None:
        """Test getting non-existent entry."""
        mock_client._ws_call.side_effect = WebSocketError("not_found: entry does not exist")

        service = IntegrationService(mock_client)
        entry = await service.get_entry("nonexistent")

        assert entry is None

    @pytest.mark.asyncio()
    async def test_get_entry_connection_error(self, mock_client: MagicMock) -> None:
        """Test that connection errors are re-raised."""
        mock_client._ws_call.side_effect = WebSocketError("Connection refused")

        service = IntegrationService(mock_client)

        with pytest.raises(WebSocketError):
            await service.get_entry("abc123")


class TestDisableEnable:
    """Tests for disable/enable operations."""

    @pytest.mark.asyncio()
    async def test_disable_entry(self, mock_client: MagicMock) -> None:
        """Test disabling an entry."""
        mock_client._ws_call.side_effect = [
            {"config_entry": {"entry_id": "abc", "domain": "test", "title": "T", "state": "loaded", "source": "user"}},
            {"require_restart": True},
        ]

        service = IntegrationService(mock_client)
        result = await service.disable_entry("abc")

        assert result["require_restart"] is True
        # Verify disable call was made with correct args
        mock_client._ws_call.assert_called_with(
            "config_entries/disable",
            entry_id="abc",
            disabled_by="user",
        )

    @pytest.mark.asyncio()
    async def test_enable_entry(self, mock_client: MagicMock) -> None:
        """Test enabling an entry."""
        mock_client._ws_call.side_effect = [
            {"config_entry": {"entry_id": "abc", "domain": "test", "title": "T", "state": "not_loaded", "source": "user"}},
            {"require_restart": False},
        ]

        service = IntegrationService(mock_client)
        result = await service.enable_entry("abc")

        assert result["require_restart"] is False
        mock_client._ws_call.assert_called_with(
            "config_entries/disable",
            entry_id="abc",
            disabled_by=None,
        )

    @pytest.mark.asyncio()
    async def test_disable_not_found(self, mock_client: MagicMock) -> None:
        """Test disabling non-existent entry."""
        mock_client._ws_call.side_effect = WebSocketError("not_found: entry does not exist")

        service = IntegrationService(mock_client)

        with pytest.raises(NotFoundError):
            await service.disable_entry("nonexistent")


class TestDeleteEntry:
    """Tests for IntegrationService.delete_entry."""

    @pytest.mark.asyncio()
    async def test_delete_entry_success(self, mock_client: MagicMock) -> None:
        """Test deleting an entry."""
        mock_client._ws_call.return_value = {
            "config_entry": {
                "entry_id": "abc123",
                "domain": "test",
                "title": "Test",
                "state": "loaded",
                "source": "user",
            }
        }
        mock_client._rest.return_value = {"require_restart": True}

        service = IntegrationService(mock_client)
        result = await service.delete_entry("abc123")

        assert result.entry_id == "abc123"
        assert result.domain == "test"
        assert result.require_restart is True

    @pytest.mark.asyncio()
    async def test_delete_entry_not_found(self, mock_client: MagicMock) -> None:
        """Test deleting non-existent entry."""
        mock_client._ws_call.side_effect = WebSocketError("not_found: entry does not exist")

        service = IntegrationService(mock_client)

        with pytest.raises(NotFoundError):
            await service.delete_entry("nonexistent")


class TestConfigFlow:
    """Tests for config flow operations."""

    @pytest.mark.asyncio()
    async def test_list_flows(self, mock_client: MagicMock) -> None:
        """Test listing in-progress flows."""
        mock_client._ws_call.return_value = [
            {
                "flow_id": "flow1",
                "handler": "zwave_js",
                "step_id": "confirm",
                "context": {"source": "usb"},
            }
        ]

        service = IntegrationService(mock_client)
        flows = await service.list_flows()

        assert len(flows) == 1
        assert flows[0].handler == "zwave_js"

    @pytest.mark.asyncio()
    async def test_get_config_flow(self, mock_client: MagicMock) -> None:
        """Test reading the current config flow step."""
        mock_client._rest.return_value = {
            "type": "form",
            "flow_id": "flow123",
            "handler": "test",
            "step_id": "battery",
            "data_schema": [{"name": "battery_type", "required": True}],
        }

        service = IntegrationService(mock_client)
        step = await service.get_flow("flow123")

        assert step.step_id == "battery"
        mock_client._rest.assert_called_once_with(
            "GET",
            "/api/config/config_entries/flow/flow123",
        )

    @pytest.mark.asyncio()
    async def test_get_options_flow(self, mock_client: MagicMock) -> None:
        """Test reading the current options flow step."""
        mock_client._rest.return_value = {
            "type": "form",
            "flow_id": "options123",
            "handler": "entry123",
            "step_id": "init",
        }

        service = IntegrationService(mock_client)
        await service.get_flow("options123", options=True)

        mock_client._rest.assert_called_once_with(
            "GET",
            "/api/config/config_entries/options/flow/options123",
        )

    @pytest.mark.asyncio()
    async def test_get_subentry_flow(self, mock_client: MagicMock) -> None:
        """Test reading the current config-subentry flow step."""
        mock_client._rest.return_value = {
            "type": "menu",
            "flow_id": "subentry123",
            "handler": "entry123",
            "step_id": "user",
            "menu_options": ["device", "entity"],
        }

        service = IntegrationService(mock_client)
        step = await service.get_flow("subentry123", subentry=True)

        assert step.menu_options == ["device", "entity"]
        mock_client._rest.assert_called_once_with(
            "GET",
            "/api/config/config_entries/subentries/flow/subentry123",
        )

    def test_flow_type_rejects_conflicting_flags(self) -> None:
        """A request cannot target two flow endpoint families."""
        with pytest.raises(ValidationError, match="both options and subentry"):
            IntegrationService._flow_type(options=True, subentry=True)

    @pytest.mark.asyncio()
    async def test_start_flow(self, mock_client: MagicMock) -> None:
        """Test starting a config flow."""
        mock_client._rest.return_value = {
            "type": "form",
            "flow_id": "flow123",
            "handler": "test",
            "step_id": "user",
            "data_schema": [],
        }

        service = IntegrationService(mock_client)
        step = await service.start_flow("test")

        assert step.flow_id == "flow123"
        assert step.type == "form"

    @pytest.mark.asyncio()
    async def test_submit_flow(self, mock_client: MagicMock) -> None:
        """Test submitting flow data."""
        mock_client._rest.return_value = {
            "type": "create_entry",
            "flow_id": "flow123",
            "handler": "test",
            "title": "Test",
            "result": {"entry_id": "abc"},
        }

        service = IntegrationService(mock_client)
        step = await service.submit_flow("flow123", {})

        assert step.is_complete is True

    @pytest.mark.asyncio()
    async def test_submit_options_flow(self, mock_client: MagicMock) -> None:
        """Test submitting data to an options flow."""
        mock_client._rest.return_value = {
            "type": "create_entry",
            "flow_id": "options123",
            "handler": "entry123",
            "title": "",
        }

        service = IntegrationService(mock_client)
        await service.submit_flow(
            "options123",
            {"threshold": 20},
            options=True,
        )

        mock_client._rest.assert_called_once_with(
            "POST",
            "/api/config/config_entries/options/flow/options123",
            json_data={"threshold": 20},
        )

    @pytest.mark.asyncio()
    async def test_submit_subentry_flow(self, mock_client: MagicMock) -> None:
        """Test submitting data to a config-subentry flow."""
        mock_client._rest.return_value = {
            "type": "form",
            "flow_id": "subentry123",
            "handler": "entry123",
            "step_id": "battery",
        }

        service = IntegrationService(mock_client)
        await service.submit_flow(
            "subentry123",
            {"source_entity_id": "sensor.lock_battery"},
            subentry=True,
        )

        mock_client._rest.assert_called_once_with(
            "POST",
            "/api/config/config_entries/subentries/flow/subentry123",
            json_data={"source_entity_id": "sensor.lock_battery"},
        )

    @pytest.mark.asyncio()
    async def test_cancel_flow(self, mock_client: MagicMock) -> None:
        """Test cancelling a flow."""
        mock_client._rest.return_value = None

        service = IntegrationService(mock_client)
        await service.cancel_flow("flow123")

        mock_client._rest.assert_called_with(
            "DELETE",
            "/api/config/config_entries/flow/flow123",
        )

    @pytest.mark.asyncio()
    async def test_cancel_options_flow(self, mock_client: MagicMock) -> None:
        """Test cancelling an options flow."""
        mock_client._rest.return_value = None

        service = IntegrationService(mock_client)
        await service.cancel_flow("options123", options=True)

        mock_client._rest.assert_called_once_with(
            "DELETE",
            "/api/config/config_entries/options/flow/options123",
        )

    @pytest.mark.asyncio()
    async def test_cancel_subentry_flow(self, mock_client: MagicMock) -> None:
        """Test cancelling a config-subentry flow."""
        mock_client._rest.return_value = None

        service = IntegrationService(mock_client)
        await service.cancel_flow("subentry123", subentry=True)

        mock_client._rest.assert_called_once_with(
            "DELETE",
            "/api/config/config_entries/subentries/flow/subentry123",
        )

    @pytest.mark.asyncio()
    async def test_start_subentry_flow(self, mock_client: MagicMock) -> None:
        """Test starting an integration-defined config-subentry flow."""
        mock_client._ws_call.return_value = {
            "config_entry": {
                "entry_id": "entry123",
                "domain": "battery_notes",
                "title": "Battery Notes",
                "state": "loaded",
                "source": "user",
            }
        }
        mock_client._rest.return_value = {
            "type": "menu",
            "flow_id": "subentry123",
            "handler": "entry123",
            "step_id": "user",
            "menu_options": ["device", "entity"],
        }

        service = IntegrationService(mock_client)
        step = await service.start_subentry_flow("entry123", "battery_note")

        assert step.menu_options == ["device", "entity"]
        mock_client._rest.assert_called_once_with(
            "POST",
            "/api/config/config_entries/subentries/flow",
            json_data={"handler": ["entry123", "battery_note"]},
        )

    @pytest.mark.asyncio()
    async def test_start_options_flow(self, mock_client: MagicMock) -> None:
        """Test starting an options flow for a supported config entry."""
        mock_client._ws_call.return_value = {
            "config_entry": {
                "entry_id": "entry123",
                "domain": "battery_notes",
                "title": "Battery Notes",
                "state": "loaded",
                "source": "user",
                "supports_options": True,
            }
        }
        mock_client._rest.return_value = {
            "type": "form",
            "flow_id": "options123",
            "handler": "entry123",
            "step_id": "init",
            "data_schema": [],
        }

        service = IntegrationService(mock_client)
        step = await service.start_options_flow("entry123")

        assert step.flow_id == "options123"
        mock_client._rest.assert_called_once_with(
            "POST",
            "/api/config/config_entries/options/flow",
            json_data={"handler": "entry123"},
        )

    @pytest.mark.asyncio()
    async def test_start_options_flow_rejects_unsupported_entry(
        self, mock_client: MagicMock
    ) -> None:
        """Test rejecting options for an entry without an options flow."""
        mock_client._ws_call.return_value = {
            "config_entry": {
                "entry_id": "entry123",
                "domain": "test",
                "title": "Test",
                "state": "loaded",
                "source": "user",
                "supports_options": False,
            }
        }

        service = IntegrationService(mock_client)
        with pytest.raises(ValidationError, match="does not support options"):
            await service.start_options_flow("entry123")


class TestSetupIntegration:
    """Tests for setup_integration high-level operation."""

    @pytest.mark.asyncio()
    async def test_setup_simple_integration(self, mock_client: MagicMock) -> None:
        """Test setting up simple integration (no input needed)."""
        # Start flow returns empty schema
        mock_client._rest.side_effect = [
            {
                "type": "form",
                "flow_id": "flow123",
                "handler": "media_extractor",
                "step_id": "user",
                "data_schema": [],
            },
            # Submit returns create_entry
            {
                "type": "create_entry",
                "flow_id": "flow123",
                "handler": "media_extractor",
                "title": "Media extractor",
                "result": {
                    "entry_id": "abc123",
                    "domain": "media_extractor",
                    "title": "Media extractor",
                },
            },
        ]

        service = IntegrationService(mock_client)
        result = await service.setup_integration("media_extractor")

        assert result.entry_id == "abc123"
        assert result.domain == "media_extractor"

    @pytest.mark.asyncio()
    async def test_setup_network_integration(self, mock_client: MagicMock) -> None:
        """Test setting up network integration with host."""
        mock_client._rest.side_effect = [
            {
                "type": "form",
                "flow_id": "flow123",
                "handler": "esphome",
                "step_id": "user",
                "data_schema": [
                    {"type": "string", "name": "host", "required": True},
                    {"type": "integer", "name": "port", "default": 6053},
                ],
            },
            {
                "type": "create_entry",
                "flow_id": "flow123",
                "handler": "esphome",
                "title": "My Device",
                "result": {
                    "entry_id": "def456",
                    "domain": "esphome",
                    "title": "My Device",
                },
            },
        ]

        service = IntegrationService(mock_client)
        result = await service.setup_integration("esphome", host="10.0.0.1")

        assert result.entry_id == "def456"
        assert result.domain == "esphome"

    @pytest.mark.asyncio()
    async def test_setup_missing_required_field(self, mock_client: MagicMock) -> None:
        """Test setup fails when required field missing."""
        mock_client._rest.side_effect = [
            {
                "type": "form",
                "flow_id": "flow123",
                "handler": "esphome",
                "step_id": "user",
                "data_schema": [
                    {"type": "string", "name": "host", "required": True},
                ],
            },
            None,  # Cancel flow
        ]

        service = IntegrationService(mock_client)

        with pytest.raises(ValidationError, match="Missing required fields.*host"):
            await service.setup_integration("esphome")  # No host provided

    @pytest.mark.asyncio()
    async def test_setup_flow_aborted(self, mock_client: MagicMock) -> None:
        """Test setup fails when flow is aborted."""
        mock_client._rest.return_value = {
            "type": "abort",
            "flow_id": "flow123",
            "handler": "test",
            "step_id": "already_configured",
        }

        service = IntegrationService(mock_client)

        with pytest.raises(ValidationError, match="aborted"):
            await service.setup_integration("test")
