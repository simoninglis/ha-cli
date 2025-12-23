"""Tests for cloud CLI commands."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from ha_cli.cli import app
from ha_cli.common.exceptions import EXIT_USAGE_ERROR, EntityFailure
from ha_cli.domains.cloud.service import AlexaEntity, CloudStatus

runner = CliRunner()


class TestCloudCLI:
    """Test cloud CLI commands."""

    def test_cloud_help(self) -> None:
        """Test cloud help shows all commands."""
        result = runner.invoke(app, ["cloud", "--help"])
        assert result.exit_code == 0
        assert "status" in result.stdout
        assert "alexa" in result.stdout

    def test_alexa_help(self) -> None:
        """Test cloud alexa help shows subcommands."""
        result = runner.invoke(app, ["cloud", "alexa", "--help"])
        assert result.exit_code == 0
        assert "entities" in result.stdout
        assert "sync" in result.stdout


class TestCloudStatusCLI:
    """Test cloud status command."""

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_status_logged_in(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test status command when logged in."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_status = AsyncMock(
            return_value=CloudStatus(
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
        )

        result = runner.invoke(app, ["cloud", "status"])
        assert result.exit_code == 0
        assert "Logged in" in result.stdout
        assert "test@example.com" in result.stdout
        assert "Cloud connected" in result.stdout

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_status_not_logged_in(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test status command when not logged in."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_status = AsyncMock(
            return_value=CloudStatus(
                logged_in=False,
                cloud_connected=False,
                remote_enabled=False,
                remote_connected=False,
                alexa_enabled=False,
                alexa_registered=False,
                google_enabled=False,
                google_registered=False,
            )
        )

        result = runner.invoke(app, ["cloud", "status"])
        assert result.exit_code == 0
        assert "Not logged in" in result.stdout

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_status_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test status command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_status = AsyncMock(
            return_value=CloudStatus(
                logged_in=True,
                cloud_connected=True,
                remote_enabled=True,
                remote_connected=True,
                alexa_enabled=True,
                alexa_registered=True,
                google_enabled=False,
                google_registered=False,
                email="test@example.com",
                alexa_entity_count=10,
            )
        )

        result = runner.invoke(app, ["cloud", "status", "--porcelain"])
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
        assert output["data"]["logged_in"] is True
        assert output["data"]["email"] == "test@example.com"

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_status_porcelain_with_issues(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test status porcelain includes issues when not logged in."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_status = AsyncMock(
            return_value=CloudStatus(
                logged_in=False,
                cloud_connected=False,
                remote_enabled=False,
                remote_connected=False,
                alexa_enabled=False,
                alexa_registered=False,
                google_enabled=False,
                google_registered=False,
            )
        )

        result = runner.invoke(app, ["cloud", "status", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["metadata"]["issues_count"] == 1
        assert "detected_issues" in output["suggestions"]
        assert len(output["suggestions"]["detected_issues"]) == 1

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_status_porcelain_healthy_no_issues(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test status porcelain has empty issues list when healthy."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_status = AsyncMock(
            return_value=CloudStatus(
                logged_in=True,
                cloud_connected=True,
                remote_enabled=True,
                remote_connected=True,
                alexa_enabled=True,
                alexa_registered=True,
                google_enabled=True,
                google_registered=True,
                email="test@example.com",
            )
        )

        result = runner.invoke(app, ["cloud", "status", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["metadata"]["issues_count"] == 0
        # detected_issues should be an empty list, not None
        assert output["suggestions"]["detected_issues"] == []

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_status_remote_ui_without_domain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test status displays Remote UI without empty parentheses when no domain."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_status = AsyncMock(
            return_value=CloudStatus(
                logged_in=True,
                cloud_connected=True,
                remote_enabled=True,
                remote_connected=True,
                alexa_enabled=False,
                alexa_registered=False,
                google_enabled=False,
                google_registered=False,
                email="test@example.com",
                remote_domain=None,  # No domain
            )
        )

        result = runner.invoke(app, ["cloud", "status"])
        assert result.exit_code == 0
        assert "Remote UI enabled" in result.stdout
        # Should NOT have empty parentheses
        assert "()" not in result.stdout


class TestCloudAlexaEntitiesCLI:
    """Test cloud alexa entities command."""

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_entities(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test alexa entities command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity(
                    entity_id="light.living_room",
                    should_expose=True,
                    display_categories=["LIGHT"],
                ),
                AlexaEntity(
                    entity_id="switch.fan",
                    should_expose=False,
                    display_categories=["SWITCH"],
                ),
            ]
        )

        result = runner.invoke(app, ["cloud", "alexa", "entities"])
        assert result.exit_code == 0
        assert "light.living_room" in result.stdout
        assert "switch.fan" in result.stdout

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_entities_exposed_only(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test alexa entities command with --exposed filter."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity(
                    entity_id="light.living_room",
                    should_expose=True,
                    display_categories=["LIGHT"],
                ),
                AlexaEntity(
                    entity_id="switch.fan",
                    should_expose=False,
                    display_categories=["SWITCH"],
                ),
            ]
        )

        result = runner.invoke(app, ["cloud", "alexa", "entities", "--exposed"])
        assert result.exit_code == 0
        assert "light.living_room" in result.stdout
        # switch.fan is not exposed, so it should not appear
        assert "switch.fan" not in result.stdout

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_entities_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test alexa entities command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity(
                    entity_id="light.living_room",
                    should_expose=True,
                    display_categories=["LIGHT"],
                ),
                AlexaEntity(
                    entity_id="switch.fan",
                    should_expose=False,
                    display_categories=["SWITCH"],
                ),
            ]
        )

        result = runner.invoke(app, ["cloud", "alexa", "entities", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        # Validate porcelain envelope structure
        assert output["status"] == "success"
        assert "command" in output
        assert "timestamp" in output
        assert "metadata" in output
        assert "data" in output
        # Validate metadata
        assert output["metadata"]["total_count"] == 2
        assert output["metadata"]["total_exposed"] == 1
        assert output["metadata"]["filtered_count"] == 2
        # Validate data content
        assert len(output["data"]) == 2
        assert output["data"][0]["entity_id"] == "light.living_room"

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_entities_porcelain_exposed_only(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test alexa entities porcelain with --exposed filter shows filter applied."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity(
                    entity_id="light.living_room",
                    should_expose=True,
                    display_categories=["LIGHT"],
                ),
                AlexaEntity(
                    entity_id="switch.fan",
                    should_expose=False,
                    display_categories=["SWITCH"],
                ),
            ]
        )

        result = runner.invoke(
            app, ["cloud", "alexa", "entities", "--exposed", "--porcelain"]
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["metadata"]["total_count"] == 2
        assert output["metadata"]["filtered_count"] == 1
        assert output["metadata"]["filters_applied"] == ["exposed_only"]


class TestCloudAlexaSyncCLI:
    """Test cloud alexa sync command."""

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_sync(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test alexa sync command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.sync_alexa = AsyncMock(return_value={"status": "ok"})

        result = runner.invoke(app, ["cloud", "alexa", "sync"])
        assert result.exit_code == 0
        assert "sync triggered" in result.stdout.lower()

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_sync_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test alexa sync command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.sync_alexa = AsyncMock(return_value={"status": "ok"})

        result = runner.invoke(app, ["cloud", "alexa", "sync", "--porcelain"])
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        # Validate porcelain envelope structure
        assert output["status"] == "success"
        assert "command" in output
        assert "timestamp" in output
        assert "data" in output
        # Validate data content
        assert output["data"]["sync_triggered"] is True


class TestCloudCLIErrors:
    """Test cloud CLI error handling."""

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_status_connection_error(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test status command handles connection errors."""
        from ha_cli.common.exceptions import ConnectionError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_status = AsyncMock(
            side_effect=ConnectionError("Failed to connect")
        )

        result = runner.invoke(app, ["cloud", "status"])
        assert result.exit_code != 0
        assert "error" in result.stdout.lower()

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_status_connection_error_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test status command handles connection errors with porcelain."""
        from ha_cli.common.exceptions import ConnectionError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_status = AsyncMock(
            side_effect=ConnectionError("Failed to connect")
        )

        result = runner.invoke(app, ["cloud", "status", "--porcelain"])
        assert result.exit_code != 0
        output = json.loads(result.stdout)
        assert output["status"] == "error"
        assert "error" in output

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_entities_websocket_error(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test alexa entities command handles WebSocket errors."""
        from ha_cli.common.exceptions import WebSocketError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_alexa_entities = AsyncMock(
            side_effect=WebSocketError("Unexpected response type")
        )

        result = runner.invoke(app, ["cloud", "alexa", "entities"])
        assert result.exit_code != 0
        assert "error" in result.stdout.lower()

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_sync_error_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test alexa sync command handles errors with porcelain."""
        from ha_cli.common.exceptions import WebSocketError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.sync_alexa = AsyncMock(
            side_effect=WebSocketError("Sync failed")
        )

        result = runner.invoke(app, ["cloud", "alexa", "sync", "--porcelain"])
        assert result.exit_code != 0
        output = json.loads(result.stdout)
        assert output["status"] == "error"

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_error_message_with_markup_is_escaped(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test error messages with Rich markup are escaped in output."""
        from ha_cli.common.exceptions import WebSocketError

        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        # Error message contains Rich markup that should be escaped
        mock_service.get_status = AsyncMock(
            side_effect=WebSocketError("[bold]Malicious[/bold] error")
        )

        result = runner.invoke(app, ["cloud", "status"])
        assert result.exit_code != 0
        # Markup should be escaped, not rendered
        assert "[bold]" in result.stdout or "\\[bold\\]" in result.stdout


class TestCloudAlexaExposeCLI:
    """Test cloud alexa expose command."""

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_expose_single_entity(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test exposing a single entity."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.set_entities_exposure = AsyncMock(
            return_value=(["light.lounge"], [])
        )

        result = runner.invoke(app, ["cloud", "alexa", "expose", "light.lounge"])
        assert result.exit_code == 0
        assert "Exposed 1 entity" in result.stdout
        assert "light.lounge" in result.stdout

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_expose_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test exposing entity with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.set_entities_exposure = AsyncMock(
            return_value=(["light.lounge"], [])
        )

        result = runner.invoke(
            app, ["cloud", "alexa", "expose", "light.lounge", "--porcelain"]
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["data"]["successful"] == ["light.lounge"]
        assert output["metadata"]["successful_count"] == 1

    @patch("ha_cli.domains.cloud.cli._parse_entity_list_yaml")
    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_expose_from_file(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Test exposing entities from a YAML file."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_parse.return_value = ["light.one", "light.two"]

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.set_entities_exposure = AsyncMock(
            return_value=(["light.one", "light.two"], [])
        )

        result = runner.invoke(
            app, ["cloud", "alexa", "expose", "--from-file", "entities.yaml"]
        )
        assert result.exit_code == 0
        assert "Exposed 2 entity" in result.stdout

    def test_alexa_expose_no_args_error(self) -> None:
        """Test expose command fails without arguments."""
        result = runner.invoke(app, ["cloud", "alexa", "expose"])
        assert result.exit_code != 0

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_expose_with_failures(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test expose command handles partial failures."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.set_entities_exposure = AsyncMock(
            return_value=(
                ["light.good"],
                [EntityFailure("light.bad", "NOT_FOUND", EXIT_USAGE_ERROR, "Entity not found")],
            )
        )

        result = runner.invoke(
            app, ["cloud", "alexa", "expose", "light.bad"]
        )
        assert result.exit_code != 0
        assert "Failed" in result.stdout


class TestCloudAlexaHideCLI:
    """Test cloud alexa hide command."""

    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_hide_single_entity(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test hiding a single entity."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.set_entities_exposure = AsyncMock(
            return_value=(["light.lounge"], [])
        )

        result = runner.invoke(app, ["cloud", "alexa", "hide", "light.lounge"])
        assert result.exit_code == 0
        assert "Hidden 1 entity" in result.stdout

    @patch("ha_cli.domains.cloud.cli._parse_entity_list_yaml")
    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_hide_all_except(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Test hiding all except entities in file."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_parse.return_value = ["light.keep"]

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity("light.keep", should_expose=True, display_categories=[]),
                AlexaEntity("light.remove", should_expose=True, display_categories=[]),
            ]
        )
        mock_service.set_entities_exposure = AsyncMock(
            return_value=(["light.remove"], [])
        )

        result = runner.invoke(
            app, ["cloud", "alexa", "hide", "--all-except", "keep.yaml"]
        )
        assert result.exit_code == 0
        assert "Hidden 1 entity" in result.stdout

    @patch("ha_cli.domains.cloud.cli._parse_entity_list_yaml")
    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_hide_all_except_nothing_to_hide(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Test hide --all-except when nothing to hide."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_parse.return_value = ["light.one"]

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity("light.one", should_expose=True, display_categories=[]),
            ]
        )

        result = runner.invoke(
            app, ["cloud", "alexa", "hide", "--all-except", "keep.yaml"]
        )
        assert result.exit_code == 0
        assert "No entities to hide" in result.stdout

    def test_alexa_hide_no_args_error(self) -> None:
        """Test hide command fails without arguments."""
        result = runner.invoke(app, ["cloud", "alexa", "hide"])
        assert result.exit_code != 0


class TestCloudAlexaSyncFilterCLI:
    """Test cloud alexa sync-filter command."""

    @patch("ha_cli.domains.cloud.cli._parse_entity_list_yaml")
    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_sync_filter_dry_run(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Test sync-filter dry run mode."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_parse.return_value = ["light.desired"]

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity("light.desired", should_expose=False, display_categories=[]),
                AlexaEntity("light.extra", should_expose=True, display_categories=[]),
            ]
        )

        result = runner.invoke(
            app,
            ["cloud", "alexa", "sync-filter", "--file", "filter.yaml", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "Dry run" in result.stdout
        assert "Would EXPOSE" in result.stdout
        assert "Would HIDE" in result.stdout

    @patch("ha_cli.domains.cloud.cli._parse_entity_list_yaml")
    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_sync_filter_applies_changes(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Test sync-filter applies changes."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_parse.return_value = ["light.desired"]

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity("light.desired", should_expose=False, display_categories=[]),
                AlexaEntity("light.extra", should_expose=True, display_categories=[]),
            ]
        )
        mock_service.set_entities_exposure = AsyncMock(
            return_value=(["light.desired"], [])
        )

        result = runner.invoke(
            app, ["cloud", "alexa", "sync-filter", "--file", "filter.yaml"]
        )
        assert result.exit_code == 0
        assert "Exposed 1 entity" in result.stdout
        assert "Hidden 1 entity" in result.stdout

    @patch("ha_cli.domains.cloud.cli._parse_entity_list_yaml")
    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_sync_filter_already_in_sync(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Test sync-filter when already in sync."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_parse.return_value = ["light.one"]

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity("light.one", should_expose=True, display_categories=[]),
            ]
        )

        result = runner.invoke(
            app, ["cloud", "alexa", "sync-filter", "--file", "filter.yaml"]
        )
        assert result.exit_code == 0
        assert "Already in sync" in result.stdout

    @patch("ha_cli.domains.cloud.cli._parse_entity_list_yaml")
    @patch("ha_cli.domains.cloud.cli.get_client_config")
    @patch("ha_cli.domains.cloud.cli.HAClient")
    @patch("ha_cli.domains.cloud.cli.CloudService")
    def test_alexa_sync_filter_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
        mock_parse: MagicMock,
    ) -> None:
        """Test sync-filter with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_parse.return_value = ["light.one"]

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service
        mock_service.get_alexa_entities = AsyncMock(
            return_value=[
                AlexaEntity("light.one", should_expose=False, display_categories=[]),
            ]
        )
        mock_service.set_entities_exposure = AsyncMock(
            return_value=(["light.one"], [])
        )

        result = runner.invoke(
            app,
            ["cloud", "alexa", "sync-filter", "--file", "filter.yaml", "--porcelain"],
        )
        assert result.exit_code == 0
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert output["data"]["exposed"] == ["light.one"]
        assert output["metadata"]["exposed_count"] == 1

    def test_alexa_sync_filter_requires_file(self) -> None:
        """Test sync-filter requires --file option."""
        result = runner.invoke(app, ["cloud", "alexa", "sync-filter"])
        assert result.exit_code != 0


class TestParseEntityListYaml:
    """Test _parse_entity_list_yaml helper function."""

    def test_parse_valid_yaml_file(self, tmp_path) -> None:
        """Test parsing valid YAML file."""
        from ha_cli.domains.cloud.cli import _parse_entity_list_yaml

        yaml_file = tmp_path / "entities.yaml"
        yaml_file.write_text("- light.one\n- light.two\n- climate.ac\n")

        result = _parse_entity_list_yaml(yaml_file)
        assert result == ["light.one", "light.two", "climate.ac"]

    def test_parse_empty_yaml_file(self, tmp_path) -> None:
        """Test parsing empty YAML file."""
        from ha_cli.domains.cloud.cli import _parse_entity_list_yaml

        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("")

        result = _parse_entity_list_yaml(yaml_file)
        assert result == []

    def test_parse_yaml_file_not_found(self, tmp_path) -> None:
        """Test parsing non-existent file raises error."""
        from ha_cli.common.exceptions import ValidationError
        from ha_cli.domains.cloud.cli import _parse_entity_list_yaml

        import pytest

        with pytest.raises(ValidationError, match="File not found"):
            _parse_entity_list_yaml(tmp_path / "nonexistent.yaml")

    def test_parse_yaml_file_not_list(self, tmp_path) -> None:
        """Test parsing YAML file with non-list content raises error."""
        from ha_cli.common.exceptions import ValidationError
        from ha_cli.domains.cloud.cli import _parse_entity_list_yaml

        import pytest

        yaml_file = tmp_path / "dict.yaml"
        yaml_file.write_text("key: value\n")

        with pytest.raises(ValidationError, match="Expected list"):
            _parse_entity_list_yaml(yaml_file)

    def test_parse_yaml_filters_invalid_entries(self, tmp_path) -> None:
        """Test parsing YAML file filters out invalid entries."""
        from ha_cli.domains.cloud.cli import _parse_entity_list_yaml

        yaml_file = tmp_path / "mixed.yaml"
        yaml_file.write_text("- light.valid\n- 123\n- \n- light.also_valid\n")

        result = _parse_entity_list_yaml(yaml_file)
        assert result == ["light.valid", "light.also_valid"]
