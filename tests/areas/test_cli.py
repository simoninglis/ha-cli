"""Tests for areas CLI commands."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from ha_cli.cli import app
from ha_cli.domains.areas.models import Area, AreaWithCounts, Floor, Label

runner = CliRunner()


class TestAreasCLI:
    """Test areas CLI commands."""

    def test_areas_help(self) -> None:
        """Test areas help shows all commands."""
        result = runner.invoke(app, ["areas", "--help"])
        assert result.exit_code == 0
        assert "list" in result.stdout
        assert "show" in result.stdout
        assert "floors" in result.stdout
        assert "labels" in result.stdout
        assert "audit" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_list_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test list command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_areas = [
            AreaWithCounts(
                area_id="kitchen",
                name="Kitchen",
                device_count=3,
                entity_count=10,
            ),
        ]
        mock_service.list_areas_with_counts = AsyncMock(return_value=test_areas)
        mock_service.get_area_summary = AsyncMock(
            return_value={"total_areas": 1, "empty_areas": 0}
        )

        result = runner.invoke(app, ["areas", "list"])
        assert result.exit_code == 0
        assert "Kitchen" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_list_command_json(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test list command with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_areas = [
            AreaWithCounts(
                area_id="kitchen",
                name="Kitchen",
                device_count=3,
                entity_count=10,
            ),
        ]
        mock_service.list_areas_with_counts = AsyncMock(return_value=test_areas)

        result = runner.invoke(app, ["areas", "list", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert isinstance(output, list)
        assert output[0]["area_id"] == "kitchen"

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_list_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test list command with porcelain output and validate structure."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_areas = [
            AreaWithCounts(
                area_id="kitchen",
                name="Kitchen",
                device_count=3,
                entity_count=10,
            ),
        ]
        mock_service.list_areas_with_counts = AsyncMock(return_value=test_areas)
        mock_service.get_area_summary = AsyncMock(
            return_value={"total_areas": 1, "empty_areas": 0}
        )

        result = runner.invoke(app, ["areas", "list", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        # Validate porcelain envelope structure
        assert output["status"] == "success"
        assert "command" in output
        assert "timestamp" in output
        assert "metadata" in output
        assert "data" in output
        assert "suggestions" in output
        # Validate data content
        assert isinstance(output["data"], list)
        assert len(output["data"]) == 1
        assert output["data"][0]["area_id"] == "kitchen"

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_show_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test show command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_area = AreaWithCounts(
            area_id="kitchen",
            name="Kitchen",
            device_count=3,
            entity_count=10,
            devices=["Light", "Sensor"],
            entities=["light.kitchen", "sensor.temp"],
        )
        mock_service.get_area = AsyncMock(return_value=test_area)

        result = runner.invoke(app, ["areas", "show", "kitchen"])
        assert result.exit_code == 0
        assert "Kitchen" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_show_command_not_found(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test show command when area not found."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_area = AsyncMock(return_value=None)

        result = runner.invoke(app, ["areas", "show", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_floors_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test floors command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_floors = [
            Floor(floor_id="ground", name="Ground Floor", level=0),
            Floor(floor_id="first", name="First Floor", level=1),
        ]
        mock_service.list_floors = AsyncMock(return_value=test_floors)

        result = runner.invoke(app, ["areas", "floors"])
        assert result.exit_code == 0
        assert "Ground Floor" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_labels_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test labels command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_labels = [
            Label(label_id="important", name="Important", color="red"),
        ]
        mock_service.list_labels = AsyncMock(return_value=test_labels)

        result = runner.invoke(app, ["areas", "labels"])
        assert result.exit_code == 0
        assert "Important" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_audit_command_no_issues(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test audit command with no issues."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_naming_issues = AsyncMock(return_value=[])
        mock_service.find_empty_areas = AsyncMock(return_value=[])
        mock_service.get_area_summary = AsyncMock(
            return_value={
                "total_areas": 5,
                "empty_areas": 0,
                "area_coverage_entities": 50,
                "area_coverage_devices": 80,
            }
        )

        result = runner.invoke(app, ["areas", "audit"])
        assert result.exit_code == 0
        assert "No issues found" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_audit_command_with_issues(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test audit command with issues."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_naming_issues = AsyncMock(
            return_value=[
                {
                    "area_id": "garrage",
                    "area_name": "Garrage",
                    "issue_type": "possible_typo",
                    "message": "Possible typo: garrage -> garage",
                }
            ]
        )
        mock_service.find_empty_areas = AsyncMock(
            return_value=[Area(area_id="empty", name="Empty Room")]
        )
        mock_service.get_area_summary = AsyncMock(
            return_value={
                "total_areas": 5,
                "empty_areas": 1,
                "area_coverage_entities": 50,
                "area_coverage_devices": 80,
            }
        )

        result = runner.invoke(app, ["areas", "audit"])
        assert result.exit_code == 1  # Exit 1 when issues found

    def test_version_command(self) -> None:
        """Test version command."""
        result = runner.invoke(app, ["areas", "version"])
        assert result.exit_code == 0
        assert "version" in result.stdout.lower()

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_show_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test show command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_area = AreaWithCounts(
            area_id="kitchen",
            name="Kitchen",
            device_count=3,
            entity_count=10,
            devices=["Light", "Sensor"],
            entities=["light.kitchen", "sensor.temp"],
        )
        mock_service.get_area = AsyncMock(return_value=test_area)

        result = runner.invoke(app, ["areas", "show", "kitchen", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert "data" in output
        assert output["data"]["area_id"] == "kitchen"

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_show_command_json(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test show command with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_area = AreaWithCounts(
            area_id="kitchen",
            name="Kitchen",
            device_count=3,
            entity_count=10,
        )
        mock_service.get_area = AsyncMock(return_value=test_area)

        result = runner.invoke(app, ["areas", "show", "kitchen", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["area_id"] == "kitchen"

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_floors_command_json(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test floors command with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_floors = [
            Floor(floor_id="ground", name="Ground Floor", level=0),
            Floor(floor_id="first", name="First Floor", level=1),
        ]
        mock_service.list_floors = AsyncMock(return_value=test_floors)

        result = runner.invoke(app, ["areas", "floors", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert isinstance(output, list)
        assert len(output) == 2
        assert output[0]["floor_id"] == "ground"

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_floors_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test floors command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_floors = [
            Floor(floor_id="ground", name="Ground Floor", level=0),
        ]
        mock_service.list_floors = AsyncMock(return_value=test_floors)

        result = runner.invoke(app, ["areas", "floors", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert "data" in output
        assert isinstance(output["data"], list)

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_labels_command_json(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test labels command with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_labels = [
            Label(label_id="important", name="Important", color="red"),
        ]
        mock_service.list_labels = AsyncMock(return_value=test_labels)

        result = runner.invoke(app, ["areas", "labels", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert isinstance(output, list)
        assert output[0]["label_id"] == "important"

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_labels_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test labels command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        test_labels = [
            Label(label_id="important", name="Important", color="red"),
        ]
        mock_service.list_labels = AsyncMock(return_value=test_labels)

        result = runner.invoke(app, ["areas", "labels", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert "data" in output
        assert isinstance(output["data"], list)

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_audit_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test audit command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_naming_issues = AsyncMock(return_value=[])
        mock_service.find_empty_areas = AsyncMock(return_value=[])
        mock_service.get_area_summary = AsyncMock(
            return_value={
                "total_areas": 5,
                "empty_areas": 0,
                "area_coverage_entities": 50,
                "area_coverage_devices": 80,
            }
        )

        result = runner.invoke(app, ["areas", "audit", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert "data" in output
        # data is the findings list directly (can be empty when no issues)
        assert isinstance(output["data"], list)
        # metadata should contain summary info
        assert "metadata" in output
        assert "total_findings" in output["metadata"]

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_audit_command_json(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test audit command with JSON output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_naming_issues = AsyncMock(return_value=[])
        mock_service.find_empty_areas = AsyncMock(return_value=[])
        mock_service.get_area_summary = AsyncMock(
            return_value={
                "total_areas": 5,
                "empty_areas": 0,
                "area_coverage_entities": 50,
                "area_coverage_devices": 80,
            }
        )

        result = runner.invoke(app, ["areas", "audit", "--json"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert "findings" in output
        assert "summary" in output

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_show_command_not_found_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test show command with porcelain when area not found."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_area = AsyncMock(return_value=None)

        result = runner.invoke(app, ["areas", "show", "nonexistent", "--porcelain"])
        assert result.exit_code == 1
        output = json.loads(result.stdout)
        assert output["status"] == "error"
        assert "error" in output


class TestAreasCRUDCLI:
    """Test areas CRUD CLI commands."""

    def test_areas_help_includes_crud_commands(self) -> None:
        """Test areas help shows CRUD commands."""
        result = runner.invoke(app, ["areas", "--help"])
        assert result.exit_code == 0
        assert "create" in result.stdout
        assert "rename" in result.stdout
        assert "update" in result.stdout
        assert "delete" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_create_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test create command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.create_area = AsyncMock(
            return_value=Area(area_id="new_area", name="New Area")
        )

        result = runner.invoke(app, ["areas", "create", "New Area"])
        assert result.exit_code == 0
        assert "Created area" in result.stdout
        assert "New Area" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_create_command_with_options(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test create command with all options."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.create_area = AsyncMock(
            return_value=Area(
                area_id="new_area",
                name="New Area",
                floor_id="ground",
                icon="mdi:home",
            )
        )

        result = runner.invoke(
            app,
            [
                "areas", "create", "New Area",
                "--floor", "ground",
                "--icon", "mdi:home",
                "--aliases", "area1, alias2",
            ]
        )
        assert result.exit_code == 0

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_create_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test create command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.create_area = AsyncMock(
            return_value=Area(area_id="new_area", name="New Area")
        )

        result = runner.invoke(app, ["areas", "create", "New Area", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["metadata"]["action"] == "created"

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_create_command_duplicate(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test create command with duplicate name."""
        from ha_cli.common.exceptions import ValidationError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.create_area = AsyncMock(
            side_effect=ValidationError("Area with name 'Existing' already exists")
        )

        result = runner.invoke(app, ["areas", "create", "Existing"])
        assert result.exit_code == 1
        assert "already exists" in result.stdout.lower()

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_rename_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test rename command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.rename_area = AsyncMock(
            return_value=Area(area_id="kitchen", name="New Kitchen")
        )

        result = runner.invoke(app, ["areas", "rename", "kitchen", "New Kitchen"])
        assert result.exit_code == 0
        assert "Renamed area" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_rename_command_not_found(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test rename command with non-existent area."""
        from ha_cli.common.exceptions import NotFoundError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.rename_area = AsyncMock(
            side_effect=NotFoundError("Area not found: nonexistent")
        )

        result = runner.invoke(app, ["areas", "rename", "nonexistent", "New Name"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_rename_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test rename command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.rename_area = AsyncMock(
            return_value=Area(area_id="kitchen", name="New Kitchen")
        )

        result = runner.invoke(
            app, ["areas", "rename", "kitchen", "New Kitchen", "--porcelain"]
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["metadata"]["action"] == "renamed"

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_update_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test update command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.update_area = AsyncMock(
            return_value=Area(area_id="kitchen", name="Kitchen", icon="mdi:kitchen")
        )

        result = runner.invoke(
            app, ["areas", "update", "kitchen", "--icon", "mdi:kitchen"]
        )
        assert result.exit_code == 0
        assert "Updated area" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_update_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test update command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.update_area = AsyncMock(
            return_value=Area(area_id="kitchen", name="Kitchen", icon="mdi:kitchen")
        )

        result = runner.invoke(
            app, ["areas", "update", "kitchen", "--icon", "mdi:kitchen", "--porcelain"]
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["metadata"]["action"] == "updated"

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_delete_command(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test delete command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_area = AsyncMock(
            return_value=AreaWithCounts(
                area_id="empty_room", name="Empty Room", device_count=0, entity_count=0
            )
        )
        mock_service.delete_area = AsyncMock()

        result = runner.invoke(app, ["areas", "delete", "empty_room"])
        assert result.exit_code == 0
        assert "Deleted area" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_delete_command_not_found(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test delete command with non-existent area."""
        from ha_cli.common.exceptions import NotFoundError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_area = AsyncMock(return_value=None)
        mock_service.delete_area = AsyncMock(
            side_effect=NotFoundError("Area not found: nonexistent")
        )

        result = runner.invoke(app, ["areas", "delete", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.stdout.lower()

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_delete_command_with_contents_no_force(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test delete command fails without force when area has contents."""
        from ha_cli.common.exceptions import ValidationError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_area = AsyncMock(
            return_value=AreaWithCounts(
                area_id="kitchen", name="Kitchen", device_count=5, entity_count=10
            )
        )
        mock_service.delete_area = AsyncMock(
            side_effect=ValidationError("Area has 5 devices. Use --force.")
        )

        result = runner.invoke(app, ["areas", "delete", "kitchen"])
        assert result.exit_code == 1
        assert "--force" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_delete_command_with_force(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test delete command with force flag."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_area = AsyncMock(
            return_value=AreaWithCounts(
                area_id="kitchen", name="Kitchen", device_count=5, entity_count=10
            )
        )
        mock_service.delete_area = AsyncMock()

        result = runner.invoke(app, ["areas", "delete", "kitchen", "--force"])
        assert result.exit_code == 0
        assert "Deleted area" in result.stdout

    @patch("ha_cli.domains.areas.cli.get_client_config")
    @patch("ha_cli.domains.areas.cli.HAClient")
    @patch("ha_cli.domains.areas.cli.AreaService")
    def test_delete_command_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test delete command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_area = AsyncMock(
            return_value=AreaWithCounts(
                area_id="empty_room", name="Empty Room", device_count=0, entity_count=0
            )
        )
        mock_service.delete_area = AsyncMock()

        result = runner.invoke(app, ["areas", "delete", "empty_room", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["metadata"]["action"] == "deleted"
