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
    _as_str_list,
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

    def test_as_str_list_with_valid_list(self):
        """Test _as_str_list returns filtered list of strings."""
        assert _as_str_list(["one", "two", "three"]) == ["one", "two", "three"]

    def test_as_str_list_filters_non_strings(self):
        """Test _as_str_list filters out non-string items."""
        assert _as_str_list(["valid", 123, None, "also_valid"]) == ["valid", "also_valid"]

    def test_as_str_list_filters_empty_strings(self):
        """Test _as_str_list filters out empty strings."""
        assert _as_str_list(["one", "", "two", ""]) == ["one", "two"]

    def test_as_str_list_with_non_list(self):
        """Test _as_str_list returns empty list for non-list input."""
        assert _as_str_list("not a list") == []
        assert _as_str_list({"key": "value"}) == []
        assert _as_str_list(None) == []
        assert _as_str_list(123) == []


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

    @pytest.mark.asyncio()
    async def test_get_status_include_entities_non_list(self, mock_client):
        """Test alexa_entity_count is 0 when include_entities is string/dict/None."""
        for invalid_value in ["entity.one", {"entity": "value"}, None]:
            mock_client._ws_call.return_value = {
                "logged_in": True,
                "cloud": "connected",
                "prefs": {},
                "alexa_entities": {
                    "include_entities": invalid_value,
                },
            }

            service = CloudService(mock_client)
            status = await service.get_status()

            assert status.alexa_entity_count == 0

    @pytest.mark.asyncio()
    async def test_get_status_registered_fields_non_bool(self, mock_client):
        """Test registered fields default to False when not booleans."""
        mock_client._ws_call.return_value = {
            "logged_in": True,
            "cloud": "connected",
            "remote_connected": "yes",  # String, not bool
            "alexa_registered": 1,  # Int, not bool
            "google_registered": "true",  # String, not bool
            "prefs": {},
            "alexa_entities": {},
        }

        service = CloudService(mock_client)
        status = await service.get_status()

        # Non-bool values should default to False
        assert status.remote_connected is False
        assert status.alexa_registered is False
        assert status.google_registered is False


def _make_registry_entry(entity_id: str, alexa_expose: bool | None = None) -> dict:
    """Helper to create entity registry entries with Alexa exposure."""
    entry = {"entity_id": entity_id, "options": {}}
    if alexa_expose is not None:
        entry["options"]["cloud.alexa"] = {"should_expose": alexa_expose}
    return entry


class TestCloudServiceGetAlexaEntities:
    """Tests for CloudService.get_alexa_entities()."""

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_success(self, mock_client):
        """Test get_alexa_entities returns parsed entities with registry exposure."""

        def ws_call_handler(command):
            if command == "cloud/alexa/entities":
                return [
                    {"entity_id": "light.living_room", "display_categories": ["LIGHT"]},
                    {"entity_id": "switch.fan", "display_categories": ["SWITCH"]},
                ]
            elif command == "config/entity_registry/list":
                return [
                    _make_registry_entry("light.living_room", alexa_expose=True),
                    _make_registry_entry("switch.fan", alexa_expose=False),
                ]
            return None

        mock_client._ws_call.side_effect = ws_call_handler

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        assert len(entities) == 2
        # Sorted by entity_id: light.living_room, switch.fan
        assert entities[0].entity_id == "light.living_room"
        assert entities[0].should_expose is True
        assert entities[1].entity_id == "switch.fan"
        assert entities[1].should_expose is False

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_skips_invalid_entity_id(self, mock_client):
        """Test get_alexa_entities skips entries with invalid entity_id."""

        def ws_call_handler(command):
            if command == "cloud/alexa/entities":
                return [
                    {"entity_id": "light.valid"},
                    {"entity_id": ""},  # Empty
                    {"entity_id": 123},  # Not string
                    {},  # Missing
                    {"entity_id": "light.another"},
                ]
            elif command == "config/entity_registry/list":
                return [
                    _make_registry_entry("light.valid", alexa_expose=True),
                    _make_registry_entry("light.another", alexa_expose=False),
                ]
            return None

        mock_client._ws_call.side_effect = ws_call_handler

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        assert len(entities) == 2
        # Results are sorted by entity_id
        assert entities[0].entity_id == "light.another"
        assert entities[1].entity_id == "light.valid"

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_exposure_from_registry(self, mock_client):
        """Test get_alexa_entities gets should_expose from entity registry."""

        def ws_call_handler(command):
            if command == "cloud/alexa/entities":
                # API doesn't return should_expose
                return [
                    {"entity_id": "light.one"},
                    {"entity_id": "light.two"},
                    {"entity_id": "light.three"},
                ]
            elif command == "config/entity_registry/list":
                # Registry has the actual exposure settings
                return [
                    _make_registry_entry("light.one", alexa_expose=True),
                    _make_registry_entry("light.two", alexa_expose=False),
                    # light.three not in registry - defaults to False
                ]
            return None

        mock_client._ws_call.side_effect = ws_call_handler

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        # Sorted by entity_id
        assert entities[0].entity_id == "light.one"
        assert entities[0].should_expose is True
        assert entities[1].entity_id == "light.three"
        assert entities[1].should_expose is False  # Not in registry
        assert entities[2].entity_id == "light.two"
        assert entities[2].should_expose is False

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_normalizes_categories(self, mock_client):
        """Test get_alexa_entities normalizes display_categories."""

        def ws_call_handler(command):
            if command == "cloud/alexa/entities":
                return [
                    {"entity_id": "light.one", "display_categories": ["LIGHT", "SWITCH"]},
                    {"entity_id": "light.two", "display_categories": "LIGHT"},  # Single string
                    {"entity_id": "light.three", "display_categories": [123, "VALID"]},  # Mixed
                    {"entity_id": "light.four"},  # Missing
                ]
            elif command == "config/entity_registry/list":
                return []
            return None

        mock_client._ws_call.side_effect = ws_call_handler

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        # Results are sorted by entity_id: four, one, three, two
        assert entities[0].display_categories == []  # light.four - missing
        assert entities[1].display_categories == ["LIGHT", "SWITCH"]  # light.one
        assert entities[2].display_categories == ["VALID"]  # light.three - non-string filtered
        assert entities[3].display_categories == ["LIGHT"]  # light.two - single string

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_filters_empty_string_categories(self, mock_client):
        """Test display_categories filters out empty strings."""

        def ws_call_handler(command):
            if command == "cloud/alexa/entities":
                return [
                    {"entity_id": "light.test", "display_categories": ["LIGHT", "", "SWITCH", ""]},
                ]
            elif command == "config/entity_registry/list":
                return []
            return None

        mock_client._ws_call.side_effect = ws_call_handler

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        assert len(entities) == 1
        # Empty strings should be filtered out
        assert entities[0].display_categories == ["LIGHT", "SWITCH"]

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_skips_non_dict_items(self, mock_client):
        """Test get_alexa_entities skips non-dict items in list."""

        def ws_call_handler(command):
            if command == "cloud/alexa/entities":
                return [
                    {"entity_id": "light.valid"},
                    "invalid_string",
                    123,
                    None,
                    {"entity_id": "light.another"},
                ]
            elif command == "config/entity_registry/list":
                return []
            return None

        mock_client._ws_call.side_effect = ws_call_handler

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

    @pytest.mark.asyncio()
    async def test_get_alexa_entities_registry_failure_graceful(self, mock_client):
        """Test get_alexa_entities handles registry fetch failure gracefully."""
        from ha_cli.common.exceptions import WebSocketError as WSError

        call_count = 0

        async def ws_call_handler(command):
            nonlocal call_count
            call_count += 1
            if command == "cloud/alexa/entities":
                return [
                    {"entity_id": "light.one"},
                    {"entity_id": "light.two"},
                ]
            elif command == "config/entity_registry/list":
                raise WSError("Registry unavailable")
            return None

        mock_client._ws_call.side_effect = ws_call_handler

        service = CloudService(mock_client)
        entities = await service.get_alexa_entities()

        # Should still return entities, but exposure defaults to False
        assert len(entities) == 2
        assert entities[0].should_expose is False
        assert entities[1].should_expose is False


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


class TestCloudServiceSetEntityExposure:
    """Tests for CloudService.set_entity_exposure()."""

    @pytest.mark.asyncio()
    async def test_set_entity_exposure_enable_success(self, mock_client):
        """Test set_entity_exposure enables exposure successfully."""
        mock_client._ws_call.return_value = {
            "entity_id": "light.lounge",
            "options": {"cloud.alexa": {"should_expose": True}},
        }

        service = CloudService(mock_client)
        result = await service.set_entity_exposure("light.lounge", True)

        assert result["entity_id"] == "light.lounge"
        mock_client._ws_call.assert_called_once_with(
            "config/entity_registry/update",
            entity_id="light.lounge",
            options_domain="cloud.alexa",
            options={"should_expose": True},
        )

    @pytest.mark.asyncio()
    async def test_set_entity_exposure_disable_success(self, mock_client):
        """Test set_entity_exposure disables exposure successfully."""
        mock_client._ws_call.return_value = {
            "entity_id": "light.lounge",
            "options": {"cloud.alexa": {"should_expose": False}},
        }

        service = CloudService(mock_client)
        result = await service.set_entity_exposure("light.lounge", False)

        assert result["entity_id"] == "light.lounge"
        mock_client._ws_call.assert_called_once_with(
            "config/entity_registry/update",
            entity_id="light.lounge",
            options_domain="cloud.alexa",
            options={"should_expose": False},
        )

    @pytest.mark.asyncio()
    async def test_set_entity_exposure_not_found(self, mock_client):
        """Test set_entity_exposure raises NotFoundError for unknown entity."""
        from ha_cli.common.exceptions import NotFoundError

        # _ws_call raises WebSocketError with format "{code}: {message}"
        mock_client._ws_call.side_effect = WebSocketError(
            "not_found: Entity not found"
        )

        service = CloudService(mock_client)

        with pytest.raises(NotFoundError, match="Entity not found: light.nonexistent"):
            await service.set_entity_exposure("light.nonexistent", True)

    @pytest.mark.asyncio()
    async def test_set_entity_exposure_unknown_error_with_not_found_message(self, mock_client):
        """Test set_entity_exposure re-raises WebSocketError when code is not 'not_found'.

        Even if the message contains 'not found', only the error code prefix
        determines whether to convert to NotFoundError.
        """
        # Error code is "unknown" not "not_found", so should re-raise as WebSocketError
        mock_client._ws_call.side_effect = WebSocketError(
            "unknown: Entity light.gone was not found"
        )

        service = CloudService(mock_client)

        with pytest.raises(WebSocketError, match="unknown"):
            await service.set_entity_exposure("light.gone", True)

    @pytest.mark.asyncio()
    async def test_set_entity_exposure_other_error(self, mock_client):
        """Test set_entity_exposure re-raises WebSocketError for other errors."""
        # _ws_call raises WebSocketError for non-not_found errors
        mock_client._ws_call.side_effect = WebSocketError(
            "validation_error: Invalid entity_id format"
        )

        service = CloudService(mock_client)

        with pytest.raises(WebSocketError, match="validation_error"):
            await service.set_entity_exposure("invalid", True)

    @pytest.mark.asyncio()
    async def test_set_entity_exposure_invalid_response_type(self, mock_client):
        """Test set_entity_exposure raises on invalid response type."""
        mock_client._ws_call.return_value = ["invalid", "list"]

        service = CloudService(mock_client)

        with pytest.raises(WebSocketError, match="Unexpected response type"):
            await service.set_entity_exposure("light.test", True)


class TestCloudServiceSetEntitiesExposure:
    """Tests for CloudService.set_entities_exposure()."""

    @pytest.mark.asyncio()
    async def test_set_entities_exposure_all_success(self, mock_client):
        """Test set_entities_exposure when all entities succeed."""
        mock_client._ws_call.return_value = {
            "entity_id": "light.test",
            "options": {"cloud.alexa": {"should_expose": True}},
        }

        service = CloudService(mock_client)
        successful, failed = await service.set_entities_exposure(
            ["light.one", "light.two", "light.three"], True
        )

        assert successful == ["light.one", "light.two", "light.three"]
        assert failed == []
        assert mock_client._ws_call.call_count == 3

    @pytest.mark.asyncio()
    async def test_set_entities_exposure_some_fail(self, mock_client):
        """Test set_entities_exposure handles partial failures."""

        async def ws_call_handler(*args, **kwargs):
            entity_id = kwargs.get("entity_id", "")
            if entity_id == "light.missing":
                # _ws_call raises WebSocketError, converted to NotFoundError
                raise WebSocketError("not_found: Entity not found")
            return {"entity_id": entity_id, "options": {}}

        mock_client._ws_call.side_effect = ws_call_handler

        service = CloudService(mock_client)
        successful, failed = await service.set_entities_exposure(
            ["light.good", "light.missing", "light.also_good"], True
        )

        assert successful == ["light.good", "light.also_good"]
        assert len(failed) == 1
        assert failed[0][0] == "light.missing"
        assert "not found" in failed[0][1].lower()

    @pytest.mark.asyncio()
    async def test_set_entities_exposure_empty_list(self, mock_client):
        """Test set_entities_exposure with empty list."""
        service = CloudService(mock_client)
        successful, failed = await service.set_entities_exposure([], True)

        assert successful == []
        assert failed == []
        mock_client._ws_call.assert_not_called()

    @pytest.mark.asyncio()
    async def test_set_entities_exposure_all_fail(self, mock_client):
        """Test set_entities_exposure when all entities fail."""
        # _ws_call raises WebSocketError for all entities
        mock_client._ws_call.side_effect = WebSocketError(
            "not_found: Entity not found"
        )

        service = CloudService(mock_client)
        successful, failed = await service.set_entities_exposure(
            ["light.one", "light.two"], True
        )

        assert successful == []
        assert len(failed) == 2
        # Verify failed list contents
        failed_ids = [entity_id for entity_id, _ in failed]
        assert "light.one" in failed_ids
        assert "light.two" in failed_ids
        # Verify error messages
        for entity_id, error_msg in failed:
            assert "not_found" in error_msg.lower() or "Entity not found" in error_msg
