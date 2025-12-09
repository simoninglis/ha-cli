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
        """Test list command with porcelain output."""
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
        assert output["status"] == "success"

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
