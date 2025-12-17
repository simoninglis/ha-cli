"""Tests for cloud CLI commands."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from ha_cli.cli import app
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
