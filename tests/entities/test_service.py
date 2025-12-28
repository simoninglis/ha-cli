"""Tests for EntityService."""

import asyncio
import json
from datetime import datetime
from io import StringIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_cli.common.exceptions import HAAutomationError
from ha_cli.common.utils import RegexValidationError
from ha_cli.domains.entities.models import (
    Entity,
    EntityImpactAnalysis,
    RenameOperation,
    RenamePreview,
    RenameResult,
)
from ha_cli.domains.entities.service import (
    EntityService,
    WS_RECV_TIMEOUT,
    parse_ws_message,
    recv_with_timeout,
)


@pytest.fixture
def mock_client():
    """Create a mock HA client."""
    client = AsyncMock()
    client.url = "http://localhost:8123"
    client.token = "test-token"
    return client


@pytest.fixture
def sample_ha_states():
    """Sample Home Assistant state data."""
    return [
        {
            "entity_id": "light.living_room",
            "state": "on",
            "attributes": {
                "friendly_name": "Living Room Light",
                "brightness": 255,
            },
            "last_changed": "2024-01-15T10:30:00.000Z",
            "last_updated": "2024-01-15T10:30:00.000Z",
        },
        {
            "entity_id": "light.bedroom",
            "state": "off",
            "attributes": {
                "friendly_name": "Bedroom Light",
            },
            "last_changed": "2024-01-15T09:00:00.000Z",
            "last_updated": "2024-01-15T09:00:00.000Z",
        },
        {
            "entity_id": "sensor.temperature",
            "state": "22.5",
            "attributes": {
                "friendly_name": "Temperature",
                "unit_of_measurement": "°C",
            },
            "last_changed": "2024-01-15T10:25:00.000Z",
            "last_updated": "2024-01-15T10:25:00.000Z",
        },
        {
            "entity_id": "climate.master_bedroom",
            "state": "cool",
            "attributes": {
                "friendly_name": "Master Bedroom AC",
                "temperature": 21,
            },
            "last_changed": "2024-01-15T08:00:00.000Z",
            "last_updated": "2024-01-15T08:00:00.000Z",
        },
    ]


@pytest.fixture
def sample_entities(sample_ha_states):
    """Convert sample states to Entity objects."""
    return [Entity.from_ha_state(state) for state in sample_ha_states]


class TestRecvWithTimeout:
    """Tests for recv_with_timeout helper."""

    @pytest.mark.asyncio
    async def test_receives_message_within_timeout(self):
        """Test receiving a message within the timeout period."""
        mock_ws = AsyncMock()
        mock_ws.recv.return_value = '{"type": "auth_ok"}'

        result = await recv_with_timeout(mock_ws, timeout=5)

        assert result == '{"type": "auth_ok"}'
        mock_ws.recv.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_raises_error(self):
        """Test that timeout raises TimeoutError."""
        mock_ws = AsyncMock()

        # Simulate a long-running recv
        async def slow_recv():
            await asyncio.sleep(10)
            return "message"

        mock_ws.recv.side_effect = slow_recv

        with pytest.raises(asyncio.TimeoutError):
            await recv_with_timeout(mock_ws, timeout=0.1)


class TestParseWsMessage:
    """Tests for parse_ws_message helper."""

    def test_parses_valid_json(self):
        """Test parsing valid JSON."""
        result = parse_ws_message('{"type": "auth_ok"}', "test")

        assert result == {"type": "auth_ok"}

    def test_raises_on_invalid_json(self):
        """Test that invalid JSON raises HAAutomationError."""
        with pytest.raises(HAAutomationError) as exc_info:
            parse_ws_message("not json", "test")

        assert "Invalid JSON" in str(exc_info.value)

    def test_raises_on_non_dict_json(self):
        """Test that non-dict JSON raises HAAutomationError."""
        with pytest.raises(HAAutomationError) as exc_info:
            parse_ws_message("[1, 2, 3]", "test")

        assert "Expected dict" in str(exc_info.value)

    def test_raises_on_non_string_input(self):
        """Test that non-string input raises HAAutomationError."""
        with pytest.raises(HAAutomationError) as exc_info:
            parse_ws_message(123, "test")  # type: ignore

        assert "Expected string" in str(exc_info.value)


class TestEntityServiceListEntities:
    """Tests for EntityService.list_entities method."""

    @pytest.mark.asyncio
    async def test_list_all_entities(self, mock_client, sample_ha_states):
        """Test listing all entities."""
        mock_client.get_states.return_value = sample_ha_states

        service = EntityService(mock_client)
        entities = await service.list_entities()

        assert len(entities) == 4
        mock_client.get_states.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_entities_with_domain_filter(self, mock_client, sample_ha_states):
        """Test listing entities filtered by domain."""
        mock_client.get_states.return_value = sample_ha_states

        service = EntityService(mock_client)
        entities = await service.list_entities(domain_filter="light")

        assert len(entities) == 2
        assert all(e.domain == "light" for e in entities)

    @pytest.mark.asyncio
    async def test_list_entities_with_search_pattern(self, mock_client, sample_ha_states):
        """Test listing entities with search pattern."""
        mock_client.get_states.return_value = sample_ha_states

        service = EntityService(mock_client)
        entities = await service.list_entities(search_pattern="living")

        assert len(entities) == 1
        assert entities[0].entity_id == "light.living_room"

    @pytest.mark.asyncio
    async def test_list_entities_with_regex_pattern(self, mock_client, sample_ha_states):
        """Test listing entities with regex pattern."""
        mock_client.get_states.return_value = sample_ha_states

        service = EntityService(mock_client)
        entities = await service.list_entities(search_pattern="^light\\.")

        assert len(entities) == 2

    @pytest.mark.asyncio
    async def test_list_entities_invalid_regex(self, mock_client, sample_ha_states):
        """Test that invalid regex raises error."""
        mock_client.get_states.return_value = sample_ha_states

        service = EntityService(mock_client)

        with pytest.raises(HAAutomationError):
            await service.list_entities(search_pattern="[invalid")

    @pytest.mark.asyncio
    async def test_list_entities_sorted_by_id(self, mock_client, sample_ha_states):
        """Test that entities are sorted by ID."""
        mock_client.get_states.return_value = sample_ha_states

        service = EntityService(mock_client)
        entities = await service.list_entities()

        entity_ids = [e.entity_id for e in entities]
        assert entity_ids == sorted(entity_ids)


class TestEntityServiceGetEntity:
    """Tests for EntityService.get_entity method."""

    @pytest.mark.asyncio
    async def test_get_existing_entity(self, mock_client, sample_ha_states):
        """Test getting an existing entity."""
        mock_client.get_states.return_value = sample_ha_states

        service = EntityService(mock_client)
        entity = await service.get_entity("light.living_room")

        assert entity is not None
        assert entity.entity_id == "light.living_room"

    @pytest.mark.asyncio
    async def test_get_nonexistent_entity(self, mock_client, sample_ha_states):
        """Test getting a non-existent entity returns None."""
        mock_client.get_states.return_value = sample_ha_states

        service = EntityService(mock_client)
        entity = await service.get_entity("nonexistent.entity")

        assert entity is None


class TestEntityServicePreviewRename:
    """Tests for EntityService.preview_rename method."""

    def test_preview_rename_basic(self, mock_client, sample_entities):
        """Test basic rename preview."""
        service = EntityService(mock_client)
        preview = service.preview_rename(
            "living_room", "lounge", sample_entities
        )

        assert preview.valid_count == 1
        assert preview.operations[0].old_entity_id == "light.living_room"
        assert preview.operations[0].new_entity_id == "light.lounge"

    def test_preview_rename_no_matches(self, mock_client, sample_entities):
        """Test preview when no entities match."""
        service = EntityService(mock_client)
        preview = service.preview_rename(
            "nonexistent", "new", sample_entities
        )

        assert preview.valid_count == 0
        assert len(preview.operations) == 0

    def test_preview_rename_regex_pattern(self, mock_client, sample_entities):
        """Test preview with regex replacement."""
        service = EntityService(mock_client)
        preview = service.preview_rename(
            "^(light\\.)(.*)", r"\1new_\2", sample_entities
        )

        assert preview.valid_count == 2
        assert "light.new_living_room" in [op.new_entity_id for op in preview.operations]

    def test_preview_rename_invalid_regex(self, mock_client, sample_entities):
        """Test preview with invalid regex raises error."""
        service = EntityService(mock_client)

        with pytest.raises(RegexValidationError):
            service.preview_rename("[invalid", "new", sample_entities)


class TestEntityServiceExecuteRenameOperations:
    """Tests for EntityService.execute_rename_operations method."""

    @pytest.mark.asyncio
    async def test_execute_empty_operations(self, mock_client):
        """Test executing empty operations list."""
        service = EntityService(mock_client)
        results = await service.execute_rename_operations([])

        assert results == []

    @pytest.mark.asyncio
    async def test_execute_rename_success(self, mock_client):
        """Test successful rename execution."""
        operation = RenameOperation(
            old_entity_id="light.old_name",
            new_entity_id="light.new_name",
            friendly_name="Test Light",
        )

        with patch("ha_cli.domains.entities.service.websockets") as mock_ws:
            mock_websocket = AsyncMock()
            mock_ws.connect.return_value.__aenter__.return_value = mock_websocket

            # Mock the WebSocket message sequence
            mock_websocket.recv.side_effect = [
                '{"type": "auth_required"}',
                '{"type": "auth_ok"}',
                '{"id": 1, "success": true}',
            ]

            service = EntityService(mock_client)
            results = await service.execute_rename_operations([operation])

            assert len(results) == 1
            assert results[0].success is True
            assert results[0].operation.old_entity_id == "light.old_name"

    @pytest.mark.asyncio
    async def test_execute_rename_failure(self, mock_client):
        """Test failed rename execution."""
        operation = RenameOperation(
            old_entity_id="light.old_name",
            new_entity_id="light.new_name",
            friendly_name="Test Light",
        )

        with patch("ha_cli.domains.entities.service.websockets") as mock_ws:
            mock_websocket = AsyncMock()
            mock_ws.connect.return_value.__aenter__.return_value = mock_websocket

            mock_websocket.recv.side_effect = [
                '{"type": "auth_required"}',
                '{"type": "auth_ok"}',
                '{"id": 1, "success": false, "error": {"message": "Entity not found"}}',
            ]

            service = EntityService(mock_client)
            results = await service.execute_rename_operations([operation])

            assert len(results) == 1
            assert results[0].success is False
            assert "Entity not found" in results[0].error_message

    @pytest.mark.asyncio
    async def test_execute_rename_auth_failure(self, mock_client):
        """Test rename with auth failure."""
        operation = RenameOperation(
            old_entity_id="light.old_name",
            new_entity_id="light.new_name",
            friendly_name="Test Light",
        )

        with patch("ha_cli.domains.entities.service.websockets") as mock_ws:
            mock_websocket = AsyncMock()
            mock_ws.connect.return_value.__aenter__.return_value = mock_websocket

            mock_websocket.recv.side_effect = [
                '{"type": "auth_required"}',
                '{"type": "auth_invalid"}',
            ]

            service = EntityService(mock_client)

            with pytest.raises(HAAutomationError) as exc_info:
                await service.execute_rename_operations([operation])

            assert "authentication failed" in str(exc_info.value).lower()


class TestEntityServiceAnalyzeEntityImpact:
    """Tests for EntityService.analyze_entity_impact method."""

    @pytest.mark.asyncio
    async def test_analyze_impact_no_references(self, mock_client):
        """Test impact analysis with no references."""
        service = EntityService(mock_client)

        # Patch the imports inside the method
        with patch.dict("sys.modules", {
            "ha_cli.domains.automations.storage.unified_automation_service": MagicMock(),
            "ha_cli.domains.dashboards.service": MagicMock(),
        }):
            with patch(
                "ha_cli.domains.automations.storage.unified_automation_service.UnifiedAutomationService"
            ) as mock_auto_svc:
                with patch(
                    "ha_cli.domains.dashboards.service.DashboardService"
                ) as mock_dash_svc:
                    mock_auto_svc.return_value.list_all = AsyncMock(return_value=[])
                    mock_dash_svc.return_value.list_dashboards = AsyncMock(return_value=[])

                    analysis = await service.analyze_entity_impact("light.test")

                    assert analysis.entity_id == "light.test"
                    assert analysis.impact_level == "low"
                    assert analysis.total_references == 0

    @pytest.mark.asyncio
    async def test_analyze_impact_with_references(self, mock_client):
        """Test impact analysis with automation and dashboard references."""
        service = EntityService(mock_client)

        # Create mock automation
        mock_automation = MagicMock()
        mock_automation.id = "test_automation"
        mock_automation.alias = "Test Automation"
        mock_automation.trigger = [{"entity_id": "light.test"}]
        mock_automation.condition = []
        mock_automation.action = []

        with patch(
            "ha_cli.domains.automations.storage.unified_automation_service.UnifiedAutomationService"
        ) as mock_auto_svc:
            with patch(
                "ha_cli.domains.dashboards.service.DashboardService"
            ) as mock_dash_svc:
                mock_auto_svc.return_value.list_all = AsyncMock(return_value=[mock_automation])
                mock_dash_svc.return_value.list_dashboards = AsyncMock(return_value=[])

                analysis = await service.analyze_entity_impact("light.test")

                assert analysis.entity_id == "light.test"
                assert len(analysis.automation_references) > 0


class TestEntityServiceDeleteEntities:
    """Tests for EntityService.delete_entities method."""

    @pytest.mark.asyncio
    async def test_delete_empty_list(self, mock_client):
        """Test deleting empty list."""
        service = EntityService(mock_client)
        results = await service.delete_entities([])

        assert results == {}

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_client):
        """Test successful entity deletion."""
        with patch("ha_cli.domains.entities.service.websockets") as mock_ws:
            mock_websocket = AsyncMock()
            mock_ws.connect.return_value.__aenter__.return_value = mock_websocket

            mock_websocket.recv.side_effect = [
                '{"type": "auth_required"}',
                '{"type": "auth_ok"}',
                '{"id": 1, "success": true}',
            ]

            service = EntityService(mock_client)
            results = await service.delete_entities(["light.test"])

            assert "light.test" in results
            assert results["light.test"]["success"] is True

    @pytest.mark.asyncio
    async def test_delete_failure(self, mock_client):
        """Test failed entity deletion."""
        with patch("ha_cli.domains.entities.service.websockets") as mock_ws:
            mock_websocket = AsyncMock()
            mock_ws.connect.return_value.__aenter__.return_value = mock_websocket

            mock_websocket.recv.side_effect = [
                '{"type": "auth_required"}',
                '{"type": "auth_ok"}',
                '{"id": 1, "success": false, "error": {"message": "Cannot delete"}}',
            ]

            service = EntityService(mock_client)
            results = await service.delete_entities(["light.test"])

            assert "light.test" in results
            assert results["light.test"]["success"] is False
            assert "Cannot delete" in results["light.test"]["error"]


class TestEntityServiceExportEntities:
    """Tests for EntityService.export_entities_to_csv method."""

    def test_export_to_csv(self, mock_client, sample_entities, tmp_path):
        """Test exporting entities to CSV."""
        output_file = str(tmp_path / "entities.csv")

        service = EntityService(mock_client)
        service.export_entities_to_csv(sample_entities, output_file)

        # Verify file exists and has correct content
        with open(output_file, "r") as f:
            content = f.read()

        assert "entity_id,friendly_name,domain,state" in content
        assert "light.living_room" in content
        assert "Living Room Light" in content


class TestEntityServiceImportOperations:
    """Tests for EntityService.import_operations_from_csv method."""

    def test_import_operations(self, mock_client, tmp_path):
        """Test importing operations from CSV."""
        csv_file = tmp_path / "operations.csv"
        csv_file.write_text(
            "old_entity_id,new_entity_id,friendly_name\n"
            "light.old,light.new,Test Light\n"
            "sensor.old,sensor.new,Test Sensor\n"
        )

        service = EntityService(mock_client)
        operations = service.import_operations_from_csv(str(csv_file))

        assert len(operations) == 2
        assert operations[0].old_entity_id == "light.old"
        assert operations[0].new_entity_id == "light.new"

    def test_import_empty_csv(self, mock_client, tmp_path):
        """Test importing from empty CSV."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("old_entity_id,new_entity_id,friendly_name\n")

        service = EntityService(mock_client)
        operations = service.import_operations_from_csv(str(csv_file))

        assert len(operations) == 0


class TestEntityServiceEntityReferencedInAutomation:
    """Tests for EntityService._entity_referenced_in_automation method."""

    def test_entity_in_trigger(self, mock_client):
        """Test finding entity in trigger."""
        mock_automation = MagicMock()
        mock_automation.trigger = [{"entity_id": "light.test"}]
        mock_automation.condition = []
        mock_automation.action = []

        service = EntityService(mock_client)
        result = service._entity_referenced_in_automation("light.test", mock_automation)

        assert result is True

    def test_entity_in_action_target(self, mock_client):
        """Test finding entity in action target."""
        mock_automation = MagicMock()
        mock_automation.trigger = []
        mock_automation.condition = []
        mock_automation.action = [
            {
                "service": "light.turn_on",
                "target": {"entity_id": "light.test"},
            }
        ]

        service = EntityService(mock_client)
        result = service._entity_referenced_in_automation("light.test", mock_automation)

        assert result is True

    def test_entity_in_entity_ids_list(self, mock_client):
        """Test finding entity in entity_ids list."""
        mock_automation = MagicMock()
        mock_automation.trigger = []
        mock_automation.condition = []
        mock_automation.action = [
            {
                "service": "light.turn_on",
                "target": {"entity_ids": ["light.one", "light.test", "light.two"]},
            }
        ]

        service = EntityService(mock_client)
        result = service._entity_referenced_in_automation("light.test", mock_automation)

        assert result is True

    def test_entity_not_referenced(self, mock_client):
        """Test entity not referenced."""
        mock_automation = MagicMock()
        mock_automation.trigger = [{"entity_id": "light.other"}]
        mock_automation.condition = []
        mock_automation.action = []

        service = EntityService(mock_client)
        result = service._entity_referenced_in_automation("light.test", mock_automation)

        assert result is False


class TestEntityServiceEntityLikelyReferenced:
    """Tests for EntityService._entity_likely_referenced_in_automation method."""

    def test_climate_entity_likely_referenced(self, mock_client):
        """Test climate entity likely referenced based on naming."""
        service = EntityService(mock_client)

        class MockAutomation:
            id = "master_bedroom_ac_on"
            alias = "Master Bedroom AC On"

        result = service._entity_likely_referenced_in_automation(
            "climate.master_bedroom", MockAutomation()
        )

        assert result is True

    def test_unrelated_automation_not_matched(self, mock_client):
        """Test unrelated automation not matched."""
        service = EntityService(mock_client)

        class MockAutomation:
            id = "kitchen_lights_on"
            alias = "Kitchen Lights On"

        result = service._entity_likely_referenced_in_automation(
            "climate.master_bedroom", MockAutomation()
        )

        assert result is False


class TestEntityServiceGetEntityRegistryEntry:
    """Tests for EntityService.get_entity_registry_entry method."""

    @pytest.mark.asyncio
    async def test_get_entity_registry_entry_success(self, mock_client):
        """Test successful entity registry entry retrieval."""
        mock_client._ws_call.return_value = {
            "entity_id": "light.living_room",
            "name": "Living Room Light",
            "icon": "mdi:lamp",
            "area_id": "living_room",
            "labels": ["indoor"],
        }

        service = EntityService(mock_client)
        result = await service.get_entity_registry_entry("light.living_room")

        assert result["entity_id"] == "light.living_room"
        assert result["name"] == "Living Room Light"
        assert result["icon"] == "mdi:lamp"
        assert result["area_id"] == "living_room"
        mock_client._ws_call.assert_called_once_with(
            "config/entity_registry/get",
            entity_id="light.living_room"
        )

    @pytest.mark.asyncio
    async def test_get_entity_registry_entry_not_found_empty_result(self, mock_client):
        """Test NotFoundError when entity registry returns empty result."""
        from ha_cli.common.exceptions import NotFoundError

        mock_client._ws_call.return_value = None

        service = EntityService(mock_client)
        with pytest.raises(NotFoundError, match="Entity not found in registry"):
            await service.get_entity_registry_entry("light.nonexistent")

    @pytest.mark.asyncio
    async def test_get_entity_registry_entry_not_found_ws_error(self, mock_client):
        """Test NotFoundError when WebSocket returns not_found error."""
        from ha_cli.common.exceptions import NotFoundError, WebSocketError

        mock_client._ws_call.side_effect = WebSocketError(
            "Entity not found",
            details={"code": "not_found"}
        )

        service = EntityService(mock_client)
        with pytest.raises(NotFoundError, match="Entity not found in registry"):
            await service.get_entity_registry_entry("light.nonexistent")


class TestEntityServiceUpdateEntityRegistry:
    """Tests for EntityService.update_entity_registry method."""

    @pytest.mark.asyncio
    async def test_update_entity_registry_name(self, mock_client):
        """Test updating entity name."""
        # Mock get_entity_registry_entry to verify entity exists
        mock_client._ws_call.side_effect = [
            # First call: get_entity_registry_entry
            {"entity_id": "light.kitchen", "name": "Old Name"},
            # Second call: update
            {"entity_id": "light.kitchen", "name": "New Kitchen Light"},
        ]

        service = EntityService(mock_client)
        result = await service.update_entity_registry(
            "light.kitchen",
            name="New Kitchen Light"
        )

        assert result["name"] == "New Kitchen Light"
        # Verify update was called with correct payload
        calls = mock_client._ws_call.call_args_list
        assert len(calls) == 2
        assert calls[1][0][0] == "config/entity_registry/update"
        assert calls[1][1]["entity_id"] == "light.kitchen"
        assert calls[1][1]["name"] == "New Kitchen Light"

    @pytest.mark.asyncio
    async def test_update_entity_registry_icon(self, mock_client):
        """Test updating entity icon."""
        mock_client._ws_call.side_effect = [
            {"entity_id": "sensor.temp", "icon": None},
            {"entity_id": "sensor.temp", "icon": "mdi:thermometer"},
        ]

        service = EntityService(mock_client)
        result = await service.update_entity_registry(
            "sensor.temp",
            icon="mdi:thermometer"
        )

        assert result["icon"] == "mdi:thermometer"

    @pytest.mark.asyncio
    async def test_update_entity_registry_area(self, mock_client):
        """Test updating entity area assignment."""
        mock_client._ws_call.side_effect = [
            {"entity_id": "switch.pump", "area_id": None},
            {"entity_id": "switch.pump", "area_id": "garage"},
        ]

        service = EntityService(mock_client)
        result = await service.update_entity_registry(
            "switch.pump",
            area_id="garage"
        )

        assert result["area_id"] == "garage"

    @pytest.mark.asyncio
    async def test_update_entity_registry_clear_icon(self, mock_client):
        """Test clearing entity icon with empty string."""
        mock_client._ws_call.side_effect = [
            {"entity_id": "light.test", "icon": "mdi:lamp"},
            {"entity_id": "light.test", "icon": None},
        ]

        service = EntityService(mock_client)
        result = await service.update_entity_registry(
            "light.test",
            icon=""  # Empty string should clear
        )

        # Verify icon was set to None in the call
        calls = mock_client._ws_call.call_args_list
        assert calls[1][1]["icon"] is None

    @pytest.mark.asyncio
    async def test_update_entity_registry_multiple_fields(self, mock_client):
        """Test updating multiple fields at once."""
        mock_client._ws_call.side_effect = [
            {"entity_id": "light.office", "name": "Old", "icon": None, "area_id": None},
            {"entity_id": "light.office", "name": "Office Desk Lamp", "icon": "mdi:desk-lamp", "area_id": "office"},
        ]

        service = EntityService(mock_client)
        result = await service.update_entity_registry(
            "light.office",
            name="Office Desk Lamp",
            icon="mdi:desk-lamp",
            area_id="office"
        )

        assert result["name"] == "Office Desk Lamp"
        assert result["icon"] == "mdi:desk-lamp"
        assert result["area_id"] == "office"

    @pytest.mark.asyncio
    async def test_update_entity_registry_not_found(self, mock_client):
        """Test updating nonexistent entity raises NotFoundError."""
        from ha_cli.common.exceptions import NotFoundError

        mock_client._ws_call.return_value = None

        service = EntityService(mock_client)
        with pytest.raises(NotFoundError, match="Entity not found in registry"):
            await service.update_entity_registry("light.nonexistent", name="Test")


class TestEntityServiceImportUpdatesFromCSV:
    """Tests for EntityService.import_updates_from_csv method."""

    def test_import_updates_basic(self, mock_client, tmp_path):
        """Test importing basic updates from CSV."""
        csv_content = """entity_id,name,icon,area_id
light.kitchen,Kitchen LED,mdi:led-strip,kitchen
sensor.temp,Temperature,mdi:thermometer,
"""
        csv_file = tmp_path / "updates.csv"
        csv_file.write_text(csv_content)

        service = EntityService(mock_client)
        operations = service.import_updates_from_csv(str(csv_file))

        assert len(operations) == 2
        assert operations[0]["entity_id"] == "light.kitchen"
        assert operations[0]["name"] == "Kitchen LED"
        assert operations[0]["icon"] == "mdi:led-strip"
        assert operations[0]["area_id"] == "kitchen"
        assert operations[1]["entity_id"] == "sensor.temp"
        assert operations[1]["name"] == "Temperature"
        assert operations[1]["icon"] == "mdi:thermometer"
        assert "area_id" not in operations[1]  # Empty = no change

    def test_import_updates_clear_values(self, mock_client, tmp_path):
        """Test CLEAR keyword clears values."""
        csv_content = """entity_id,name,icon,area_id
light.test,,CLEAR,CLEAR
"""
        csv_file = tmp_path / "updates.csv"
        csv_file.write_text(csv_content)

        service = EntityService(mock_client)
        operations = service.import_updates_from_csv(str(csv_file))

        assert len(operations) == 1
        assert operations[0]["entity_id"] == "light.test"
        assert "name" not in operations[0]  # Empty = no change
        assert operations[0]["icon"] == ""  # CLEAR = empty string
        assert operations[0]["area_id"] == ""  # CLEAR = empty string

    def test_import_updates_empty_rows_skipped(self, mock_client, tmp_path):
        """Test empty entity_id rows are skipped."""
        csv_content = """entity_id,name,icon,area_id
light.valid,Valid Name,,
,Invalid Row,,
"""
        csv_file = tmp_path / "updates.csv"
        csv_file.write_text(csv_content)

        service = EntityService(mock_client)
        operations = service.import_updates_from_csv(str(csv_file))

        assert len(operations) == 1
        assert operations[0]["entity_id"] == "light.valid"

    def test_import_updates_no_changes_skipped(self, mock_client, tmp_path):
        """Test rows with no actual changes are skipped."""
        csv_content = """entity_id,name,icon,area_id
light.nochange,,,
"""
        csv_file = tmp_path / "updates.csv"
        csv_file.write_text(csv_content)

        service = EntityService(mock_client)
        operations = service.import_updates_from_csv(str(csv_file))

        assert len(operations) == 0
