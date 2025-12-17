"""Tests for CloudService."""

from unittest.mock import AsyncMock

import pytest

from ha_cli.common.exceptions import WebSocketError
from ha_cli.domains.cloud.service import (
    AlexaEntity,
    CloudService,
    CloudStatus,
    _as_bool,
    _as_str,
)


class TestHelperFunctions:
    """Tests for type validation helper functions."""

    def test_as_bool_with_true(self):
        """Test _as_bool returns True for boolean True."""
        assert _as_bool(True) is True

    def test_as_bool_with_false(self):
        """Test _as_bool returns False for boolean False."""
        assert _as_bool(False) is False

    def test_as_bool_with_string_returns_default(self):
        """Test _as_bool returns default for string 'true'."""
        assert _as_bool("true") is False
        assert _as_bool("true", True) is True

    def test_as_bool_with_string_false_returns_default(self):
        """Test _as_bool returns default for string 'false' (not coerced)."""
        assert _as_bool("false") is False
        assert _as_bool("false", True) is True

    def test_as_bool_with_none(self):
        """Test _as_bool returns default for None."""
        assert _as_bool(None) is False
        assert _as_bool(None, True) is True

    def test_as_bool_with_int(self):
        """Test _as_bool returns default for integers (not coerced)."""
        assert _as_bool(1) is False
        assert _as_bool(0) is False

    def test_as_str_with_string(self):
        """Test _as_str returns string for valid string."""
        assert _as_str("hello") == "hello"

    def test_as_str_with_empty_string(self):
        """Test _as_str returns None for empty string."""
        assert _as_str("") is None

    def test_as_str_with_none(self):
        """Test _as_str returns None for None."""
        assert _as_str(None) is None

    def test_as_str_with_int(self):
        """Test _as_str returns None for non-string types."""
        assert _as_str(123) is None

    def test_as_str_with_dict(self):
        """Test _as_str returns None for dict."""
        assert _as_str({"key": "value"}) is None


class TestCloudStatus:
    """Tests for CloudStatus dataclass."""

    def test_to_dict(self):
        """Test CloudStatus.to_dict() returns correct dictionary."""
        status = CloudStatus(
            logged_in=True,
            cloud_connected=True,
            remote_enabled=True,
            remote_connected=True,
            alexa_enabled=True,
            alexa_registered=True,
            google_enabled=False,
            google_registered=False,
            email="test@example.com",
            subscription_expiration="2025-12-31",
            remote_domain="test.ui.nabu.casa",
            alexa_entity_count=42,
        )
        result = status.to_dict()

        assert result["logged_in"] is True
        assert result["cloud_connected"] is True
        assert result["email"] == "test@example.com"
        assert result["alexa_entity_count"] == 42


class TestAlexaEntity:
    """Tests for AlexaEntity dataclass."""

    def test_to_dict(self):
        """Test AlexaEntity.to_dict() returns correct dictionary."""
        entity = AlexaEntity(
            entity_id="light.living_room",
            should_expose=True,
            display_categories=["LIGHT"],
        )
        result = entity.to_dict()

        assert result["entity_id"] == "light.living_room"
        assert result["should_expose"] is True
        assert result["display_categories"] == ["LIGHT"]


@pytest.fixture()
def mock_client():
    """Create a mock HA client."""
    client = AsyncMock()
    client.url = "http://localhost:8123"
    client.token = "test-token"
    return client


class TestCloudServiceGetStatus:
    """Tests for CloudService.get_status()."""

    @pytest.mark.asyncio()
    async def test_get_status_logged_in(self, mock_client):
        """Test get_status when logged in."""
        mock_client._ws_call.return_value = {
            "logged_in": True,
            "cloud": "connected",
            "remote_connected": True,
            "alexa_registered": True,
            "google_registered": False,
            "email": "test@example.com",
            "subscription_expiration": "2025-12-31",
            "remote_domain": "test.ui.nabu.casa",
            "prefs": {
                "remote_enabled": True,
                "alexa_enabled": True,
                "google_enabled": False,
            },
            "alexa_entities": {
                "include_entities": ["light.one", "light.two"],
            },
        }

        service = CloudService(mock_client)
        status = await service.get_status()

        assert status.logged_in is True
        assert status.cloud_connected is True
        assert status.remote_enabled is True
        assert status.alexa_enabled is True
        assert status.alexa_registered is True
        assert status.email == "test@example.com"
        assert status.alexa_entity_count == 2
        mock_client._ws_call.assert_called_once_with("cloud/status")

    @pytest.mark.asyncio()
    async def test_get_status_not_logged_in(self, mock_client):
        """Test get_status when not logged in."""
        mock_client._ws_call.return_value = {
            "logged_in": False,
        }

        service = CloudService(mock_client)
        status = await service.get_status()

        assert status.logged_in is False
        assert status.cloud_connected is False
        assert status.alexa_enabled is False

    @pytest.mark.asyncio()
    async def test_get_status_cloud_boolean_true(self, mock_client):
        """Test get_status handles cloud as boolean True."""
        mock_client._ws_call.return_value = {
            "logged_in": True,
            "cloud": True,  # Boolean instead of string
            "prefs": {},
            "alexa_entities": {},
        }

        service = CloudService(mock_client)
        status = await service.get_status()

        assert status.cloud_connected is True

    @pytest.mark.asyncio()
    async def test_get_status_cloud_disconnected(self, mock_client):
        """Test get_status handles disconnected cloud."""
        mock_client._ws_call.return_value = {
            "logged_in": True,
            "cloud": "disconnected",
            "prefs": {},
            "alexa_entities": {},
        }

        service = CloudService(mock_client)
        status = await service.get_status()

        assert status.cloud_connected is False

    @pytest.mark.asyncio()
    async def test_get_status_malformed_prefs(self, mock_client):
        """Test get_status handles malformed prefs (not a dict)."""
        mock_client._ws_call.return_value = {
            "logged_in": True,
            "cloud": "connected",
            "prefs": "invalid",  # Should be dict
            "alexa_entities": {},
        }

        service = CloudService(mock_client)
        status = await service.get_status()

        # Should use defaults when prefs is malformed
        assert status.remote_enabled is False
        assert status.alexa_enabled is False

    @pytest.mark.asyncio()
    async def test_get_status_malformed_alexa_entities(self, mock_client):
        """Test get_status handles malformed alexa_entities."""
        mock_client._ws_call.return_value = {
            "logged_in": True,
            "cloud": "connected",
            "prefs": {},
            "alexa_entities": "invalid",  # Should be dict
        }

        service = CloudService(mock_client)
        status = await service.get_status()

        assert status.alexa_entity_count == 0

    @pytest.mark.asyncio()
    async def test_get_status_invalid_response_type(self, mock_client):
        """Test get_status raises on invalid response type."""
        mock_client._ws_call.return_value = ["invalid", "list"]

        service = CloudService(mock_client)

        with pytest.raises(WebSocketError, match="Unexpected cloud/status response type"):
            await service.get_status()

    @pytest.mark.asyncio()
    async def test_get_status_validates_string_fields(self, mock_client):
        """Test get_status validates email/domain are strings."""
        mock_client._ws_call.return_value = {
            "logged_in": True,
            "cloud": "connected",
            "email": 12345,  # Not a string
            "remote_domain": {"invalid": "dict"},  # Not a string
            "prefs": {},
            "alexa_entities": {},
        }

        service = CloudService(mock_client)
        status = await service.get_status()

        # Should be None when not valid strings
        assert status.email is None
        assert status.remote_domain is None

    @pytest.mark.asyncio()
    async def test_get_status_alexa_entity_count_validates_strings(self, mock_client):
        """Test alexa_entity_count only counts valid non-empty strings."""
        mock_client._ws_call.return_value = {
            "logged_in": True,
            "cloud": "connected",
            "prefs": {},
            "alexa_entities": {
                "include_entities": [
                    "light.valid_one",
                    "light.valid_two",
                    123,  # Not a string
                    "",  # Empty string
                    None,  # None
                    "light.valid_three",
                ],
            },
        }

        service = CloudService(mock_client)
        status = await service.get_status()

        # Should only count the 3 valid non-empty strings
        assert status.alexa_entity_count == 3


class TestCloudServiceGetAlexaEntities:
    """Tests for CloudService.get_alexa_entities()."""

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_success(self, mock_client):
        """Test get_alexa_entities returns parsed entities."""
        mock_client._ws_call.return_value = [
            {
                "entity_id": "light.living_room",
                "should_expose": True,
                "display_categories": ["LIGHT"],
            },
            {
                "entity_id": "switch.fan",
                "should_expose": False,
                "display_categories": ["SWITCH"],
            },
        ]

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        assert len(entities) == 2
        assert entities[0].entity_id == "light.living_room"
        assert entities[0].should_expose is True
        assert entities[1].should_expose is False
        mock_client._ws_call.assert_called_once_with("cloud/alexa/entities")

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_skips_invalid_entity_id(self, mock_client):
        """Test get_alexa_entities skips entries with invalid entity_id."""
        mock_client._ws_call.return_value = [
            {"entity_id": "light.valid", "should_expose": True},
            {"entity_id": "", "should_expose": True},  # Empty
            {"entity_id": 123, "should_expose": True},  # Not string
            {"should_expose": True},  # Missing
            {"entity_id": "light.another", "should_expose": False},
        ]

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        assert len(entities) == 2
        assert entities[0].entity_id == "light.valid"
        assert entities[1].entity_id == "light.another"

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_handles_should_expose_strings(self, mock_client):
        """Test get_alexa_entities only accepts bool for should_expose."""
        mock_client._ws_call.return_value = [
            {"entity_id": "light.one", "should_expose": True},
            {"entity_id": "light.two", "should_expose": "true"},  # String, not bool
            {"entity_id": "light.three", "should_expose": "false"},  # String
        ]

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        assert entities[0].should_expose is True
        # Strings should default to False (not coerced)
        assert entities[1].should_expose is False
        assert entities[2].should_expose is False

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_normalizes_categories(self, mock_client):
        """Test get_alexa_entities normalizes display_categories."""
        mock_client._ws_call.return_value = [
            {"entity_id": "light.one", "display_categories": ["LIGHT", "SWITCH"]},
            {"entity_id": "light.two", "display_categories": "LIGHT"},  # Single string
            {"entity_id": "light.three", "display_categories": [123, "VALID"]},  # Mixed
            {"entity_id": "light.four"},  # Missing
        ]

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        assert entities[0].display_categories == ["LIGHT", "SWITCH"]
        assert entities[1].display_categories == ["LIGHT"]
        assert entities[2].display_categories == ["VALID"]  # Non-string filtered
        assert entities[3].display_categories == []

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_skips_non_dict_items(self, mock_client):
        """Test get_alexa_entities skips non-dict items in list."""
        mock_client._ws_call.return_value = [
            {"entity_id": "light.valid", "should_expose": True},
            "invalid_string",
            123,
            None,
            {"entity_id": "light.another", "should_expose": False},
        ]

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        assert len(entities) == 2

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_invalid_response_type(self, mock_client):
        """Test get_alexa_entities raises on invalid response type."""
        mock_client._ws_call.return_value = {"not": "a list"}

        service = CloudService(mock_client)

        with pytest.raises(WebSocketError, match="Unexpected cloud/alexa/entities"):
            await service.get_alexa_entities()


class TestCloudServiceSyncAlexa:
    """Tests for CloudService.sync_alexa()."""

    @pytest.mark.asyncio()
    async def test_sync_alexa_success_with_dict(self, mock_client):
        """Test sync_alexa returns dict response."""
        mock_client._ws_call.return_value = {"status": "ok"}

        service = CloudService(mock_client)
        result = await service.sync_alexa()

        assert result == {"status": "ok"}
        mock_client._ws_call.assert_called_once_with("cloud/alexa/sync")

    @pytest.mark.asyncio()
    async def test_sync_alexa_success_with_none(self, mock_client):
        """Test sync_alexa handles None response."""
        mock_client._ws_call.return_value = None

        service = CloudService(mock_client)
        result = await service.sync_alexa()

        assert result == {}

    @pytest.mark.asyncio()
    async def test_sync_alexa_invalid_response_type(self, mock_client):
        """Test sync_alexa raises on invalid response type."""
        mock_client._ws_call.return_value = ["invalid", "list"]

        service = CloudService(mock_client)

        with pytest.raises(WebSocketError, match="Unexpected cloud/alexa/sync"):
            await service.sync_alexa()
