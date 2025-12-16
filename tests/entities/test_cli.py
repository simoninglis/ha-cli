"""Tests for entity CLI commands."""

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from ha_cli.domains.entities import cli
from ha_cli.domains.entities.models import (
    Entity,
    EntityImpactAnalysis,
    RenameOperation,
    RenamePreview,
    RenameResult,
)


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture(autouse=True)
def setup_env(monkeypatch):
    """Set up environment variables for testing."""
    monkeypatch.setenv("HA_URL", "http://localhost:8123")
    monkeypatch.setenv("HA_TOKEN", "test-token")


@pytest.fixture
def sample_entities():
    """Sample entity list for testing."""
    return [
        Entity(
            entity_id="light.living_room",
            friendly_name="Living Room Light",
            domain="light",
            state="on",
            attributes={"brightness": 255},
        ),
        Entity(
            entity_id="light.bedroom",
            friendly_name="Bedroom Light",
            domain="light",
            state="off",
            attributes={},
        ),
        Entity(
            entity_id="sensor.temperature",
            friendly_name="Temperature Sensor",
            domain="sensor",
            state="22.5",
            attributes={"unit_of_measurement": "°C"},
        ),
        Entity(
            entity_id="climate.master_bedroom",
            friendly_name="Master Bedroom AC",
            domain="climate",
            state="cool",
            attributes={"temperature": 21},
        ),
    ]


@pytest.fixture
def sample_impact_analysis():
    """Sample impact analysis for testing."""
    return EntityImpactAnalysis.create(
        entity_id="light.living_room",
        automation_refs=["automation.living_room_lights"],
        dashboard_refs=["mobile/View 1"],
    )


class TestStateCommand:
    """Tests for the state command."""

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_state_basic(self, mock_service_class, mock_client_class, runner):
        """Test basic state query."""
        mock_service = AsyncMock()
        mock_service.get_state.return_value = {
            "entity_id": "light.office",
            "state": "on",
            "attributes": {"brightness": 255, "friendly_name": "Office Light"},
            "last_changed": "2025-12-16T10:00:00Z",
            "last_updated": "2025-12-16T10:05:00Z",
        }
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["state", "light.office"])

        assert result.exit_code == 0
        assert "light.office" in result.output
        assert "on" in result.output
        assert "Office Light" in result.output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_state_with_attributes(self, mock_service_class, mock_client_class, runner):
        """Test state query with attributes flag."""
        mock_service = AsyncMock()
        mock_service.get_state.return_value = {
            "entity_id": "light.office",
            "state": "on",
            "attributes": {"brightness": 255, "color_temp": 370, "friendly_name": "Office Light"},
            "last_changed": "2025-12-16T10:00:00Z",
        }
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["state", "light.office", "--attributes"])

        assert result.exit_code == 0
        assert "brightness" in result.output
        assert "255" in result.output
        assert "color_temp" in result.output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_state_value_only(self, mock_service_class, mock_client_class, runner):
        """Test state query with value-only flag."""
        mock_service = AsyncMock()
        mock_service.get_state.return_value = {
            "entity_id": "sensor.temperature",
            "state": "22.5",
            "attributes": {"unit_of_measurement": "°C"},
        }
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["state", "sensor.temperature", "--value-only"])

        assert result.exit_code == 0
        # Output should be just the state value with newline
        assert result.output.strip() == "22.5"

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_state_porcelain(self, mock_service_class, mock_client_class, runner):
        """Test state query with porcelain output."""
        mock_service = AsyncMock()
        mock_service.get_state.return_value = {
            "entity_id": "light.office",
            "state": "on",
            "attributes": {"brightness": 255},
            "last_changed": "2025-12-16T10:00:00Z",
            "last_updated": "2025-12-16T10:05:00Z",
        }
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["state", "light.office", "--porcelain"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["status"] == "success"
        assert output["data"]["entity_id"] == "light.office"
        assert output["data"]["state"] == "on"
        assert "metadata" in output

    def test_state_mutually_exclusive_flags(self, runner):
        """Test that --value-only and --porcelain are mutually exclusive."""
        result = runner.invoke(cli.app, ["state", "light.office", "--value-only", "--porcelain"])

        assert result.exit_code != 0
        assert "Cannot use --value-only and --porcelain together" in result.output

    def test_state_invalid_entity_id_format(self, runner):
        """Test error on invalid entity_id format."""
        result = runner.invoke(cli.app, ["state", "invalid_entity"])

        assert result.exit_code != 0
        assert "Invalid entity_id format" in result.output

    def test_state_invalid_entity_id_format_multiple_dots(self, runner):
        """Test error on entity_id with multiple dots."""
        result = runner.invoke(cli.app, ["state", "light.office.extra"])

        assert result.exit_code != 0
        assert "Invalid entity_id format" in result.output


class TestListCommand:
    """Tests for the list command."""

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_list_basic(self, mock_service_class, mock_client_class, runner, sample_entities):
        """Test basic entity listing."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["list"])

        assert result.exit_code == 0
        assert "light.living_room" in result.output
        assert "Living Room Light" in result.output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_list_with_domain_filter(self, mock_service_class, mock_client_class, runner, sample_entities):
        """Test entity listing with domain filter."""
        mock_service = AsyncMock()
        light_entities = [e for e in sample_entities if e.domain == "light"]
        mock_service.list_entities.return_value = light_entities
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["list", "--domain", "light"])

        assert result.exit_code == 0
        mock_service.list_entities.assert_called_once()
        call_args = mock_service.list_entities.call_args
        assert call_args[0][1] == "light" or call_args.kwargs.get("domain_filter") == "light"

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_list_with_search_pattern(self, mock_service_class, mock_client_class, runner, sample_entities):
        """Test entity listing with search pattern."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["list", "--search", "living"])

        assert result.exit_code == 0

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_list_json_output(self, mock_service_class, mock_client_class, runner, sample_entities):
        """Test entity listing with JSON output."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["list", "--json"])

        assert result.exit_code == 0
        # Should be valid JSON
        output = json.loads(result.output)
        assert isinstance(output, list)
        assert len(output) == 4

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    @patch("ha_cli.domains.entities.cli.get_home_assistant_health")
    def test_list_porcelain_output(
        self, mock_health, mock_service_class, mock_client_class, runner, sample_entities
    ):
        """Test entity listing with porcelain output."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        mock_health.return_value = {"healthy": True}

        result = runner.invoke(cli.app, ["list", "--porcelain"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["status"] == "success"
        assert "metadata" in output
        assert "data" in output

    def test_list_mutually_exclusive_flags(self, runner):
        """Test that --json and --porcelain are mutually exclusive."""
        result = runner.invoke(cli.app, ["list", "--json", "--porcelain"])

        assert result.exit_code != 0
        assert "Cannot use --json and --porcelain together" in result.output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_list_empty_results(self, mock_service_class, mock_client_class, runner):
        """Test listing when no entities found."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = []
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["list"])

        assert result.exit_code == 0
        assert "No entities found" in result.output


class TestExportCommand:
    """Tests for the export command."""

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_export_to_csv(self, mock_service_class, mock_client_class, runner, sample_entities, tmp_path):
        """Test exporting entities to CSV."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities
        mock_service.export_entities_to_csv = MagicMock()
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        output_file = str(tmp_path / "entities.csv")
        result = runner.invoke(cli.app, ["export", output_file])

        assert result.exit_code == 0
        assert "Exported" in result.output
        mock_service.export_entities_to_csv.assert_called_once()

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_export_with_domain_filter(
        self, mock_service_class, mock_client_class, runner, sample_entities, tmp_path
    ):
        """Test exporting with domain filter."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities
        mock_service.export_entities_to_csv = MagicMock()
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        output_file = str(tmp_path / "entities.csv")
        result = runner.invoke(cli.app, ["export", output_file, "--domain", "light"])

        assert result.exit_code == 0


class TestBackupCommand:
    """Tests for the backup command."""

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_backup_auto_filename(self, mock_service_class, mock_client_class, runner, sample_entities):
        """Test backup with auto-generated filename."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities
        mock_service.export_entities_to_csv = MagicMock()
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        with patch("ha_cli.domains.entities.cli.Path") as mock_path:
            result = runner.invoke(cli.app, ["backup"])

        assert result.exit_code == 0
        assert "Backed up" in result.output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_backup_custom_filename(
        self, mock_service_class, mock_client_class, runner, sample_entities, tmp_path
    ):
        """Test backup with custom filename."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities
        mock_service.export_entities_to_csv = MagicMock()
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        output_file = str(tmp_path / "custom_backup.csv")
        result = runner.invoke(cli.app, ["backup", "--output", output_file])

        assert result.exit_code == 0


class TestRenameCommand:
    """Tests for the rename command."""

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_rename_dry_run(self, mock_service_class, mock_client_class, runner, sample_entities):
        """Test rename with dry run."""
        mock_service = MagicMock()
        mock_service.list_entities = AsyncMock(return_value=sample_entities)
        mock_service.analyze_entity_impact = AsyncMock(
            return_value=EntityImpactAnalysis.create("light.living_room", [], [])
        )

        preview = RenamePreview(
            operations=[
                RenameOperation(
                    old_entity_id="light.living_room",
                    new_entity_id="light.lounge",
                    friendly_name="Living Room Light",
                )
            ],
            total_count=1,
            valid_count=1,
        )
        mock_service.preview_rename.return_value = preview
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            cli.app, ["rename", "--search", "living", "--replace", "lounge", "--dry-run"]
        )

        assert result.exit_code == 0
        assert "Dry run mode" in result.output
        mock_service.execute_rename_operations.assert_not_called()

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_rename_no_matches(self, mock_service_class, mock_client_class, runner):
        """Test rename when no entities match."""
        mock_service = MagicMock()
        mock_service.list_entities = AsyncMock(return_value=[])
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            cli.app, ["rename", "--search", "nonexistent", "--replace", "new"]
        )

        assert result.exit_code == 0
        assert "No entities found" in result.output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_rename_with_confirmation_abort(
        self, mock_service_class, mock_client_class, runner, sample_entities
    ):
        """Test rename aborted by user."""
        mock_service = MagicMock()
        mock_service.list_entities = AsyncMock(return_value=sample_entities)
        mock_service.analyze_entity_impact = AsyncMock(
            return_value=EntityImpactAnalysis.create("light.living_room", [], [])
        )

        preview = RenamePreview(
            operations=[
                RenameOperation(
                    old_entity_id="light.living_room",
                    new_entity_id="light.lounge",
                    friendly_name="Living Room Light",
                )
            ],
            total_count=1,
            valid_count=1,
        )
        mock_service.preview_rename.return_value = preview
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        # Simulate user typing 'n' to abort
        result = runner.invoke(
            cli.app, ["rename", "--search", "living", "--replace", "lounge"], input="n\n"
        )

        assert result.exit_code == 0
        assert "cancelled" in result.output.lower()


class TestAnalyzeCommand:
    """Tests for the analyze command."""

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_analyze_single_entity(
        self, mock_service_class, mock_client_class, runner, sample_entities, sample_impact_analysis
    ):
        """Test analyzing a single entity."""
        mock_service = AsyncMock()
        mock_service.get_entity.return_value = sample_entities[0]
        mock_service.analyze_entity_impact.return_value = sample_impact_analysis
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["analyze", "light.living_room"])

        assert result.exit_code == 0
        assert "light.living_room" in result.output
        assert "Impact" in result.output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_analyze_single_entity_json(
        self, mock_service_class, mock_client_class, runner, sample_entities, sample_impact_analysis
    ):
        """Test analyzing single entity with JSON output."""
        mock_service = AsyncMock()
        mock_service.get_entity.return_value = sample_entities[0]
        mock_service.analyze_entity_impact.return_value = sample_impact_analysis
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["analyze", "light.living_room", "--json"])

        assert result.exit_code == 0
        # The output includes extra console text before JSON, find the JSON portion
        output_lines = result.output.strip().split("\n")
        json_start = None
        for i, line in enumerate(output_lines):
            if line.strip().startswith("{"):
                json_start = i
                break
        assert json_start is not None, "No JSON found in output"
        json_text = "\n".join(output_lines[json_start:])
        output = json.loads(json_text)
        assert output["entity_id"] == "light.living_room"
        assert "automation_references" in output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_analyze_entity_not_found(self, mock_service_class, mock_client_class, runner):
        """Test analyzing a non-existent entity."""
        mock_service = AsyncMock()
        mock_service.get_entity.return_value = None
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["analyze", "nonexistent.entity"])

        # Should fail with error about entity not found
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_analyze_batch_with_search(
        self, mock_service_class, mock_client_class, runner, sample_entities
    ):
        """Test batch analysis with search pattern."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities[:2]  # lights only
        mock_service.analyze_entity_impact.return_value = EntityImpactAnalysis.create(
            "light.living_room", [], []
        )
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["analyze", "--search", "light"])

        assert result.exit_code == 0
        assert "Batch Analysis" in result.output

    def test_analyze_requires_entity_or_filter(self, runner):
        """Test that analyze requires either entity_id or search/domain filter."""
        result = runner.invoke(cli.app, ["analyze"])

        assert result.exit_code != 0
        assert "Must provide either entity_id or search/domain" in result.output


class TestDeleteCommand:
    """Tests for the delete command."""

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_delete_dry_run(self, mock_service_class, mock_client_class, runner, sample_entities):
        """Test delete with dry run."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities[:1]
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            cli.app, ["delete", "--search", "living", "--dry-run"]
        )

        assert result.exit_code == 0
        assert "Dry run mode" in result.output
        mock_service.delete_entities.assert_not_called()

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_delete_with_force(self, mock_service_class, mock_client_class, runner, sample_entities):
        """Test delete with force flag skips confirmation."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities[:1]
        mock_service.delete_entities.return_value = {
            "light.living_room": {"success": True}
        }
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["delete", "--search", "living", "--force"])

        assert result.exit_code == 0
        mock_service.delete_entities.assert_called_once()

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_delete_specific_entity_ids(
        self, mock_service_class, mock_client_class, runner, sample_entities
    ):
        """Test deleting specific entity IDs."""
        mock_service = AsyncMock()
        mock_service.get_entity.return_value = sample_entities[0]
        mock_service.delete_entities.return_value = {
            "light.living_room": {"success": True}
        }
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            cli.app,
            ["delete", "--entity-id", "light.living_room", "--force"],
        )

        assert result.exit_code == 0

    def test_delete_requires_search_or_entity_ids(self, runner):
        """Test that delete requires either search or entity_ids."""
        result = runner.invoke(cli.app, ["delete", "--force"])

        assert result.exit_code != 0
        assert "Must provide either --search pattern or --entity-id" in result.output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_delete_no_entities_found(self, mock_service_class, mock_client_class, runner):
        """Test delete when no entities match."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = []
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["delete", "--search", "nonexistent", "--force"])

        assert result.exit_code == 0
        assert "No entities found" in result.output

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_delete_json_output(self, mock_service_class, mock_client_class, runner, sample_entities):
        """Test delete with JSON output."""
        mock_service = AsyncMock()
        mock_service.list_entities.return_value = sample_entities[:1]
        mock_service.delete_entities.return_value = {
            "light.living_room": {"success": True}
        }
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            cli.app, ["delete", "--search", "living", "--force", "--json"]
        )

        assert result.exit_code == 0
        # The output may contain multiple JSON objects (preview + results)
        # Find the last complete JSON object which is the results
        json_objects = []
        lines = result.output.strip().split("\n")
        current_json = []
        brace_count = 0
        for line in lines:
            if "{" in line or brace_count > 0:
                current_json.append(line)
                brace_count += line.count("{") - line.count("}")
                if brace_count == 0 and current_json:
                    json_objects.append("\n".join(current_json))
                    current_json = []

        # Take the last JSON object (results)
        assert len(json_objects) > 0, "No JSON objects found in output"
        output = json.loads(json_objects[-1])
        assert "results" in output or "entities_to_delete" in output

    def test_delete_mutually_exclusive_output_flags(self, runner):
        """Test that --json and --porcelain are mutually exclusive."""
        result = runner.invoke(
            cli.app, ["delete", "--search", "test", "--json", "--porcelain", "--force"]
        )

        assert result.exit_code != 0


class TestVersionCommand:
    """Tests for the version command."""

    def test_version(self, runner):
        """Test version command."""
        result = runner.invoke(cli.app, ["version"])

        assert result.exit_code == 0
        assert "ha-cli entities version" in result.output


class TestImportOperationsCommand:
    """Tests for the import_operations command."""

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_import_file_not_found(self, mock_service_class, mock_client_class, runner):
        """Test import with non-existent file."""
        result = runner.invoke(cli.app, ["import-operations", "nonexistent.csv"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_import_dry_run(self, mock_service_class, mock_client_class, runner, tmp_path):
        """Test import with dry run."""
        # Create a test CSV file
        csv_file = tmp_path / "operations.csv"
        csv_file.write_text(
            "old_entity_id,new_entity_id,friendly_name\n"
            "light.old_name,light.new_name,Test Light\n"
        )

        mock_service = MagicMock()
        mock_service.import_operations_from_csv.return_value = [
            RenameOperation(
                old_entity_id="light.old_name",
                new_entity_id="light.new_name",
                friendly_name="Test Light",
            )
        ]
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["import-operations", str(csv_file), "--dry-run"])

        assert result.exit_code == 0
        assert "Dry run mode" in result.output
        mock_service.execute_rename_operations.assert_not_called()

    @patch("ha_cli.domains.entities.cli.HAClient")
    @patch("ha_cli.domains.entities.cli.EntityService")
    def test_import_empty_file(self, mock_service_class, mock_client_class, runner, tmp_path):
        """Test import with empty CSV file."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("old_entity_id,new_entity_id,friendly_name\n")

        mock_service = MagicMock()
        mock_service.import_operations_from_csv.return_value = []
        mock_service_class.return_value = mock_service

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli.app, ["import-operations", str(csv_file)])

        assert result.exit_code == 0
        assert "No rename operations found" in result.output
