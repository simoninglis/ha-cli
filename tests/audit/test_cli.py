"""Tests for audit CLI commands (ha_cli/domains/audit/cli.py)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from typer.testing import CliRunner

from ha_cli.cli import app
from ha_cli.domains.audit.models import AuditFinding, AuditResult, AuditSeverity

runner = CliRunner()


class TestAuditCLI:
    """Test audit CLI commands."""

    def test_audit_help(self) -> None:
        """Test audit help shows all commands."""
        result = runner.invoke(app, ["audit", "--help"])
        assert result.exit_code == 0
        assert "dead-entities" in result.stdout
        assert "unused-automations" in result.stdout
        assert "broken-automations" in result.stdout
        assert "fragile-automations" in result.stdout
        assert "trigger-stats" in result.stdout
        assert "integrations" in result.stdout
        assert "duplicates" in result.stdout
        assert "all" in result.stdout

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_dead_entities_no_findings(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test dead-entities command with no findings."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        # Empty result - use AsyncMock for async method
        mock_service.check_dead_entities = AsyncMock(
            return_value=AuditResult(check_name="dead-entities", findings=[])
        )

        result = runner.invoke(app, ["audit", "dead-entities"])
        assert result.exit_code == 0
        assert "No issues found" in result.stdout

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_dead_entities_with_findings(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test dead-entities command with findings."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        # Result with findings
        mock_service.check_dead_entities = AsyncMock(
            return_value=AuditResult(
                check_name="dead-entities",
                findings=[
                    AuditFinding(
                        entity_id="sensor.broken",
                        severity=AuditSeverity.ERROR,
                        message="Entity unavailable",
                        category="dead-entities",
                    )
                ],
            )
        )

        result = runner.invoke(app, ["audit", "dead-entities"])
        # Exit code 1 indicates findings
        assert result.exit_code == 1
        assert "sensor.broken" in result.stdout

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_dead_entities_porcelain(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test dead-entities command with porcelain output."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_dead_entities = AsyncMock(
            return_value=AuditResult(check_name="dead-entities", findings=[])
        )

        result = runner.invoke(app, ["audit", "dead-entities", "--porcelain"])
        assert result.exit_code == 0
        # Should be valid JSON
        output = json.loads(result.stdout)
        assert output["status"] == "success"
        assert "data" in output

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_unused_automations(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test unused-automations command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_unused_automations = AsyncMock(
            return_value=AuditResult(check_name="unused-automations", findings=[])
        )

        result = runner.invoke(app, ["audit", "unused-automations"])
        assert result.exit_code == 0

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_unused_automations_with_days(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test unused-automations command with custom days."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_unused_automations = AsyncMock(
            return_value=AuditResult(check_name="unused-automations", findings=[])
        )

        result = runner.invoke(app, ["audit", "unused-automations", "--days", "90"])
        assert result.exit_code == 0

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_broken_automations(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test broken-automations command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_broken_automations = AsyncMock(
            return_value=AuditResult(check_name="broken-automations", findings=[])
        )

        result = runner.invoke(app, ["audit", "broken-automations"])
        assert result.exit_code == 0

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_fragile_automations(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test fragile-automations command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_fragile_automations = AsyncMock(
            return_value=AuditResult(check_name="fragile-automations", findings=[])
        )

        result = runner.invoke(app, ["audit", "fragile-automations"])
        assert result.exit_code == 0

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_trigger_stats(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test trigger-stats command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_trigger_stats = AsyncMock(
            return_value=AuditResult(check_name="trigger-stats", findings=[])
        )

        result = runner.invoke(app, ["audit", "trigger-stats"])
        assert result.exit_code == 0

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_integrations(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test integrations command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_integrations = AsyncMock(
            return_value=AuditResult(check_name="integrations", findings=[])
        )

        result = runner.invoke(app, ["audit", "integrations"])
        assert result.exit_code == 0

    @patch("ha_cli.domains.audit.cli.get_client_config")
    @patch("ha_cli.domains.audit.cli.HAClient")
    @patch("ha_cli.domains.audit.cli.AuditService")
    def test_duplicates(
        self,
        mock_service_class: MagicMock,
        mock_client_class: MagicMock,
        mock_config: MagicMock,
    ) -> None:
        """Test duplicates command."""
        mock_config.return_value = ("http://test:8123", "test-token")
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_service = MagicMock()
        mock_service_class.return_value = mock_service

        mock_service.check_duplicates = AsyncMock(
            return_value=AuditResult(check_name="duplicates", findings=[])
        )

        result = runner.invoke(app, ["audit", "duplicates"])
        assert result.exit_code == 0
