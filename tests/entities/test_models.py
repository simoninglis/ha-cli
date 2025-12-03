"""Tests for entity domain models."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ha_cli.domains.entities.models import (
    Entity,
    EntityImpactAnalysis,
    RenameOperation,
    RenamePreview,
    RenameResult,
)


class TestEntity:
    """Tests for Entity model."""

    def test_entity_creation_basic(self):
        """Test basic entity creation."""
        entity = Entity(
            entity_id="light.living_room",
            friendly_name="Living Room Light",
            domain="light",
            state="on",
        )

        assert entity.entity_id == "light.living_room"
        assert entity.friendly_name == "Living Room Light"
        assert entity.domain == "light"
        assert entity.state == "on"

    def test_entity_creation_with_defaults(self):
        """Test entity creation with default values."""
        entity = Entity(
            entity_id="sensor.test",
            domain="sensor",
        )

        assert entity.friendly_name == ""
        assert entity.state == ""
        assert entity.attributes == {}
        assert entity.last_changed is None
        assert entity.last_updated is None

    def test_entity_from_ha_state(self):
        """Test creating entity from Home Assistant state data."""
        state_data = {
            "entity_id": "light.test",
            "state": "on",
            "attributes": {
                "friendly_name": "Test Light",
                "brightness": 255,
            },
            "last_changed": "2024-01-15T10:30:00.000Z",
            "last_updated": "2024-01-15T10:30:00.000Z",
        }

        entity = Entity.from_ha_state(state_data)

        assert entity.entity_id == "light.test"
        assert entity.domain == "light"
        assert entity.friendly_name == "Test Light"
        assert entity.state == "on"
        assert entity.attributes["brightness"] == 255
        assert entity.last_changed is not None

    def test_entity_from_ha_state_without_friendly_name(self):
        """Test creating entity when friendly_name is not provided."""
        state_data = {
            "entity_id": "sensor.unknown",
            "state": "unavailable",
            "attributes": {},
        }

        entity = Entity.from_ha_state(state_data)

        assert entity.friendly_name == ""

    def test_entity_from_ha_state_invalid_timestamp(self):
        """Test creating entity with invalid timestamp."""
        state_data = {
            "entity_id": "sensor.test",
            "state": "on",
            "attributes": {},
            "last_changed": "invalid-date",
            "last_updated": None,
        }

        entity = Entity.from_ha_state(state_data)

        assert entity.last_changed is None
        assert entity.last_updated is None

    def test_entity_to_dict(self):
        """Test converting entity to dictionary."""
        entity = Entity(
            entity_id="light.test",
            friendly_name="Test",
            domain="light",
            state="on",
            last_changed=datetime(2024, 1, 15, 10, 30, 0),
        )

        data = entity.to_dict()

        assert data["entity_id"] == "light.test"
        assert data["friendly_name"] == "Test"
        assert data["domain"] == "light"
        assert data["state"] == "on"
        assert "2024-01-15" in data["last_changed"]

    def test_entity_id_null_char_stripped(self):
        """Test that NULL characters are stripped from entity_id."""
        entity = Entity(
            entity_id="light.test\x00extra",
            domain="light",
        )

        assert "\x00" not in entity.entity_id


class TestRenameOperation:
    """Tests for RenameOperation model."""

    def test_rename_operation_creation(self):
        """Test basic rename operation creation."""
        op = RenameOperation(
            old_entity_id="light.old",
            new_entity_id="light.new",
            friendly_name="Test",
        )

        assert op.old_entity_id == "light.old"
        assert op.new_entity_id == "light.new"
        assert op.friendly_name == "Test"

    def test_validate_ids_valid(self):
        """Test validation passes for valid IDs."""
        op = RenameOperation(
            old_entity_id="light.old",
            new_entity_id="light.new",
        )

        issues = op.validate_ids()

        assert len(issues) == 0

    def test_validate_ids_identical(self):
        """Test validation fails for identical IDs."""
        op = RenameOperation(
            old_entity_id="light.same",
            new_entity_id="light.same",
        )

        issues = op.validate_ids()

        assert any("identical" in issue for issue in issues)

    def test_validate_ids_invalid_old_format(self):
        """Test validation fails for invalid old entity ID format."""
        op = RenameOperation(
            old_entity_id="invalid",
            new_entity_id="light.new",
        )

        issues = op.validate_ids()

        assert any("Invalid old entity ID" in issue for issue in issues)

    def test_validate_ids_invalid_new_format(self):
        """Test validation fails for invalid new entity ID format."""
        op = RenameOperation(
            old_entity_id="light.old",
            new_entity_id="invalid",
        )

        issues = op.validate_ids()

        assert any("Invalid new entity ID" in issue for issue in issues)

    def test_validate_ids_domain_change(self):
        """Test validation fails for domain change."""
        op = RenameOperation(
            old_entity_id="light.test",
            new_entity_id="switch.test",
        )

        issues = op.validate_ids()

        assert any("Domain change not allowed" in issue for issue in issues)

    def test_validate_ids_empty_old(self):
        """Test validation fails for empty old entity ID."""
        op = RenameOperation(
            old_entity_id="",
            new_entity_id="light.new",
        )

        issues = op.validate_ids()

        assert len(issues) > 0


class TestRenamePreview:
    """Tests for RenamePreview model."""

    def test_from_operations_all_valid(self):
        """Test creating preview from all valid operations."""
        operations = [
            RenameOperation(old_entity_id="light.a", new_entity_id="light.new_a"),
            RenameOperation(old_entity_id="light.b", new_entity_id="light.new_b"),
        ]

        preview = RenamePreview.from_operations(operations)

        assert preview.total_count == 2
        assert preview.valid_count == 2
        assert len(preview.invalid_operations) == 0

    def test_from_operations_with_invalid(self):
        """Test creating preview with some invalid operations."""
        operations = [
            RenameOperation(old_entity_id="light.valid", new_entity_id="light.new"),
            RenameOperation(old_entity_id="invalid", new_entity_id="also_invalid"),
        ]

        preview = RenamePreview.from_operations(operations)

        assert preview.total_count == 2
        assert preview.valid_count == 1
        assert len(preview.invalid_operations) == 1

    def test_from_operations_large_batch_warning(self):
        """Test warning for large operation batches."""
        operations = [
            RenameOperation(
                old_entity_id=f"light.entity_{i}",
                new_entity_id=f"light.new_entity_{i}",
            )
            for i in range(60)
        ]

        preview = RenamePreview.from_operations(operations)

        assert any("Large number of operations" in w for w in preview.warnings)

    def test_from_operations_many_domains_warning(self):
        """Test warning for operations spanning many domains."""
        domains = ["light", "sensor", "switch", "cover", "climate", "binary_sensor"]
        operations = [
            RenameOperation(
                old_entity_id=f"{d}.entity",
                new_entity_id=f"{d}.new_entity",
            )
            for d in domains
        ]

        preview = RenamePreview.from_operations(operations)

        assert any("many domains" in w for w in preview.warnings)


class TestRenameResult:
    """Tests for RenameResult model."""

    def test_rename_result_success(self):
        """Test successful rename result."""
        op = RenameOperation(
            old_entity_id="light.old",
            new_entity_id="light.new",
        )
        result = RenameResult(
            operation=op,
            success=True,
        )

        assert result.success is True
        assert result.error_message is None

    def test_rename_result_failure(self):
        """Test failed rename result."""
        op = RenameOperation(
            old_entity_id="light.old",
            new_entity_id="light.new",
        )
        result = RenameResult(
            operation=op,
            success=False,
            error_message="Entity not found",
        )

        assert result.success is False
        assert result.error_message == "Entity not found"

    def test_rename_result_to_dict(self):
        """Test converting rename result to dictionary."""
        op = RenameOperation(
            old_entity_id="light.old",
            new_entity_id="light.new",
            friendly_name="Test",
        )
        result = RenameResult(
            operation=op,
            success=True,
            timestamp=datetime(2024, 1, 15, 10, 30, 0),
        )

        data = result.to_dict()

        assert data["old_entity_id"] == "light.old"
        assert data["new_entity_id"] == "light.new"
        assert data["success"] is True
        assert "2024-01-15" in data["timestamp"]


class TestEntityImpactAnalysis:
    """Tests for EntityImpactAnalysis model."""

    def test_create_no_references(self):
        """Test creating analysis with no references."""
        analysis = EntityImpactAnalysis.create(
            entity_id="light.test",
            automation_refs=[],
            dashboard_refs=[],
        )

        assert analysis.entity_id == "light.test"
        assert analysis.impact_level == "low"
        assert analysis.total_references == 0
        assert "No references found" in analysis.recommendations[0]

    def test_create_low_references(self):
        """Test creating analysis with few references (medium impact)."""
        analysis = EntityImpactAnalysis.create(
            entity_id="light.test",
            automation_refs=["automation.one", "automation.two"],
            dashboard_refs=["mobile/view1"],
        )

        assert analysis.impact_level == "medium"
        assert analysis.total_references == 3

    def test_create_high_references(self):
        """Test creating analysis with many references (high impact)."""
        automation_refs = [f"automation.{i}" for i in range(5)]
        dashboard_refs = [f"dashboard.{i}" for i in range(3)]

        analysis = EntityImpactAnalysis.create(
            entity_id="light.test",
            automation_refs=automation_refs,
            dashboard_refs=dashboard_refs,
        )

        assert analysis.impact_level == "high"
        assert analysis.total_references == 8

    def test_create_recommendations_for_automations(self):
        """Test recommendations include automation review."""
        analysis = EntityImpactAnalysis.create(
            entity_id="light.test",
            automation_refs=["automation.one"],
            dashboard_refs=[],
        )

        assert any("automation" in r.lower() for r in analysis.recommendations)

    def test_create_recommendations_for_dashboards(self):
        """Test recommendations include dashboard update."""
        analysis = EntityImpactAnalysis.create(
            entity_id="light.test",
            automation_refs=[],
            dashboard_refs=["mobile/view1"],
        )

        assert any("dashboard" in r.lower() for r in analysis.recommendations)

    def test_create_performance_recommendation(self):
        """Test performance recommendation for many references."""
        analysis = EntityImpactAnalysis.create(
            entity_id="light.test",
            automation_refs=[f"a{i}" for i in range(8)],
            dashboard_refs=[f"d{i}" for i in range(5)],
        )

        assert any("performance" in r.lower() for r in analysis.recommendations)


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.parametrize(
        "entity_id,expected_domain",
        [
            ("light.test", "light"),
            ("sensor.temperature_kitchen", "sensor"),
            ("binary_sensor.motion", "binary_sensor"),
            ("climate.master_bedroom", "climate"),
            ("automation.my_automation", "automation"),
        ],
    )
    def test_entity_domain_extraction(self, entity_id, expected_domain):
        """Test domain extraction from various entity IDs."""
        state_data = {
            "entity_id": entity_id,
            "state": "on",
            "attributes": {},
        }
        entity = Entity.from_ha_state(state_data)

        assert entity.domain == expected_domain

    @pytest.mark.parametrize(
        "old_id,new_id,should_be_valid",
        [
            ("light.old", "light.new", True),
            ("sensor.temp", "sensor.temperature", True),
            ("light.old", "switch.old", False),  # Domain change
            ("invalid", "light.new", False),  # Invalid old
            ("light.old", "invalid", False),  # Invalid new
            ("light.same", "light.same", False),  # Same IDs
        ],
    )
    def test_rename_operation_validation(self, old_id, new_id, should_be_valid):
        """Test rename operation validation with various inputs."""
        op = RenameOperation(
            old_entity_id=old_id,
            new_entity_id=new_id,
        )
        issues = op.validate_ids()

        if should_be_valid:
            assert len(issues) == 0
        else:
            assert len(issues) > 0

    @pytest.mark.parametrize(
        "auto_refs,dash_refs,expected_level",
        [
            ([], [], "low"),
            (["a1"], [], "medium"),
            ([], ["d1", "d2"], "medium"),
            (["a1", "a2"], ["d1", "d2", "d3"], "medium"),
            (["a1", "a2", "a3", "a4", "a5", "a6"], [], "high"),
            (["a1", "a2", "a3"], ["d1", "d2", "d3"], "high"),
        ],
    )
    def test_impact_level_calculation(self, auto_refs, dash_refs, expected_level):
        """Test impact level calculation with various reference counts."""
        analysis = EntityImpactAnalysis.create(
            entity_id="light.test",
            automation_refs=auto_refs,
            dashboard_refs=dash_refs,
        )

        assert analysis.impact_level == expected_level

    def test_entity_with_special_characters_in_name(self):
        """Test entity with special characters in friendly name."""
        state_data = {
            "entity_id": "sensor.special",
            "state": "on",
            "attributes": {
                "friendly_name": "Temperature (°C) - Kitchen [Main]",
            },
        }
        entity = Entity.from_ha_state(state_data)

        assert "°C" in entity.friendly_name
        assert "[Main]" in entity.friendly_name

    def test_entity_with_empty_state(self):
        """Test entity with empty state."""
        state_data = {
            "entity_id": "sensor.unavailable",
            "state": "",
            "attributes": {},
        }
        entity = Entity.from_ha_state(state_data)

        assert entity.state == ""

    def test_entity_with_none_state(self):
        """Test entity with None state raises validation error.

        The Entity model requires state to be a string. When Home Assistant
        returns None for state, the caller should handle this by providing
        a default value before creating the Entity.
        """
        import pydantic

        state_data = {
            "entity_id": "sensor.unavailable",
            "state": None,
            "attributes": {},
        }

        # The current implementation does not handle None states gracefully
        # This is expected behavior - state must be a string
        with pytest.raises(pydantic.ValidationError):
            Entity.from_ha_state(state_data)
