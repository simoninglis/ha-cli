"""Tests for audit domain models."""

from datetime import datetime, timezone

import pytest

from ha_cli.domains.audit.models import (
    AuditFinding,
    AuditResult,
    AuditSeverity,
    BrokenAutomationFinding,
    DeadEntityFinding,
    DuplicateEntityFinding,
    IntegrationHealthSummary,
    TriggerStatsFinding,
    UnusedAutomationFinding,
)


class TestAuditSeverity:
    """Tests for AuditSeverity enum."""

    def test_severity_values(self) -> None:
        """Test severity enum values."""
        assert AuditSeverity.ERROR.value == "error"
        assert AuditSeverity.WARNING.value == "warning"
        assert AuditSeverity.INFO.value == "info"

    def test_severity_from_string(self) -> None:
        """Test creating severity from string."""
        assert AuditSeverity("error") == AuditSeverity.ERROR
        assert AuditSeverity("warning") == AuditSeverity.WARNING
        assert AuditSeverity("info") == AuditSeverity.INFO


class TestAuditFinding:
    """Tests for AuditFinding base class."""

    def test_basic_finding(self) -> None:
        """Test creating a basic finding."""
        finding = AuditFinding(
            severity=AuditSeverity.WARNING,
            category="test",
            message="Test message",
        )
        assert finding.severity == AuditSeverity.WARNING
        assert finding.category == "test"
        assert finding.message == "Test message"
        assert finding.entity_id is None
        assert finding.automation_id is None

    def test_finding_with_entity(self) -> None:
        """Test finding with entity ID."""
        finding = AuditFinding(
            severity=AuditSeverity.ERROR,
            category="test",
            message="Entity error",
            entity_id="light.test",
            suggested_action="Check entity",
        )
        assert finding.entity_id == "light.test"
        assert finding.suggested_action == "Check entity"

    def test_finding_to_dict(self) -> None:
        """Test converting finding to dictionary."""
        finding = AuditFinding(
            severity=AuditSeverity.WARNING,
            category="test",
            message="Test",
            entity_id="sensor.temp",
            details={"extra": "data"},
        )
        result = finding.to_dict()

        assert result["severity"] == "warning"
        assert result["category"] == "test"
        assert result["entity_id"] == "sensor.temp"
        assert result["details"] == {"extra": "data"}


class TestDeadEntityFinding:
    """Tests for DeadEntityFinding."""

    def test_dead_entity_finding(self) -> None:
        """Test creating a dead entity finding."""
        finding = DeadEntityFinding(
            severity=AuditSeverity.ERROR,
            category="dead-entities",
            message="Entity unavailable",
            entity_id="light.broken",
            state="unavailable",
            integration="hue",
        )
        assert finding.category == "dead-entities"
        assert finding.state == "unavailable"
        assert finding.integration == "hue"

    def test_dead_entity_to_dict(self) -> None:
        """Test dead entity to dict includes state and integration."""
        now = datetime.now(timezone.utc)
        finding = DeadEntityFinding(
            severity=AuditSeverity.WARNING,
            category="dead-entities",
            message="Entity unknown",
            entity_id="sensor.old",
            state="unknown",
            integration="mqtt",
            last_changed=now,
        )
        result = finding.to_dict()

        assert result["state"] == "unknown"
        assert result["integration"] == "mqtt"
        assert "last_changed" in result


class TestDuplicateEntityFinding:
    """Tests for DuplicateEntityFinding."""

    def test_duplicate_finding(self) -> None:
        """Test creating a duplicate entity finding."""
        finding = DuplicateEntityFinding(
            severity=AuditSeverity.WARNING,
            category="duplicates",
            message="Duplicate entity",
            entity_id="sensor.temp_2",
            base_entity_id="sensor.temp",
            suffix="2",
            all_duplicates=["sensor.temp", "sensor.temp_2", "sensor.temp_3"],
        )
        assert finding.base_entity_id == "sensor.temp"
        assert finding.suffix == "2"
        assert len(finding.all_duplicates) == 3

    def test_duplicate_to_dict(self) -> None:
        """Test duplicate finding to dict."""
        finding = DuplicateEntityFinding(
            severity=AuditSeverity.WARNING,
            category="duplicates",
            message="Duplicate",
            entity_id="light.test_2",
            base_entity_id="light.test",
            suffix="2",
            all_duplicates=["light.test", "light.test_2"],
        )
        result = finding.to_dict()

        assert result["base_entity_id"] == "light.test"
        assert result["suffix"] == "2"
        assert result["all_duplicates"] == ["light.test", "light.test_2"]


class TestBrokenAutomationFinding:
    """Tests for BrokenAutomationFinding."""

    def test_broken_automation_finding(self) -> None:
        """Test creating a broken automation finding."""
        finding = BrokenAutomationFinding(
            severity=AuditSeverity.ERROR,
            category="broken-automations",
            message="Missing entity",
            automation_id="motion_light",
            referenced_entity="sensor.deleted",
            entity_exists=False,
            entity_available=False,
            reference_location="trigger",
        )
        assert finding.automation_id == "motion_light"
        assert finding.referenced_entity == "sensor.deleted"
        assert finding.entity_exists is False
        assert finding.reference_location == "trigger"

    def test_fragile_automation_finding(self) -> None:
        """Test fragile automation category is set when entity exists but unavailable."""
        finding = BrokenAutomationFinding(
            severity=AuditSeverity.WARNING,
            category="fragile-automations",
            message="Unavailable entity",
            automation_id="climate_control",
            referenced_entity="climate.bedroom",
            entity_exists=True,
            entity_available=False,
            reference_location="action",
        )
        assert finding.category == "fragile-automations"
        assert finding.entity_exists is True

    def test_broken_automation_to_dict(self) -> None:
        """Test broken automation to dict."""
        finding = BrokenAutomationFinding(
            severity=AuditSeverity.ERROR,
            category="broken-automations",
            message="Test",
            automation_id="test_auto",
            referenced_entity="light.missing",
            entity_exists=False,
            entity_available=False,
            reference_location="condition",
        )
        result = finding.to_dict()

        assert result["referenced_entity"] == "light.missing"
        assert result["entity_exists"] is False
        assert result["reference_location"] == "condition"


class TestUnusedAutomationFinding:
    """Tests for UnusedAutomationFinding."""

    def test_never_triggered_finding(self) -> None:
        """Test finding for never triggered automation."""
        finding = UnusedAutomationFinding(
            severity=AuditSeverity.WARNING,
            category="unused-automations",
            message="Never triggered",
            automation_id="unused_auto",
            automation_name="Unused Automation",
            last_triggered=None,
            days_since_trigger=None,
            is_enabled=True,
        )
        assert finding.last_triggered is None
        assert finding.days_since_trigger is None
        assert finding.is_enabled is True

    def test_old_triggered_finding(self) -> None:
        """Test finding for automation not triggered in long time."""
        old_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
        finding = UnusedAutomationFinding(
            severity=AuditSeverity.INFO,
            category="unused-automations",
            message="Not triggered in 100 days",
            automation_id="old_auto",
            automation_name="Old Automation",
            last_triggered=old_date,
            days_since_trigger=100,
            is_enabled=True,
        )
        assert finding.last_triggered == old_date
        assert finding.days_since_trigger == 100

    def test_unused_automation_to_dict(self) -> None:
        """Test unused automation to dict."""
        finding = UnusedAutomationFinding(
            severity=AuditSeverity.INFO,
            category="unused-automations",
            message="Test",
            automation_id="test",
            automation_name="Test Auto",
            days_since_trigger=50,
            is_enabled=False,
        )
        result = finding.to_dict()

        assert result["automation_name"] == "Test Auto"
        assert result["days_since_trigger"] == 50
        assert result["is_enabled"] is False


class TestTriggerStatsFinding:
    """Tests for TriggerStatsFinding."""

    def test_trigger_stats_finding(self) -> None:
        """Test creating a trigger stats finding."""
        finding = TriggerStatsFinding(
            severity=AuditSeverity.INFO,
            category="trigger-stats",
            message="Automation stats",
            automation_id="motion_light",
            automation_name="Motion Light",
            trigger_count=3,
            is_enabled=True,
        )
        assert finding.trigger_count == 3
        assert finding.is_enabled is True


class TestIntegrationHealthSummary:
    """Tests for IntegrationHealthSummary."""

    def test_healthy_integration(self) -> None:
        """Test creating a healthy integration summary."""
        summary = IntegrationHealthSummary(
            integration="hue",
            total_entities=10,
            available_entities=9,
            unavailable_entities=1,
            unknown_entities=0,
            health_percentage=90.0,
            domains={"light": 8, "sensor": 2},
        )
        assert summary.health_percentage == 90.0
        assert summary.total_entities == 10

    def test_unhealthy_integration(self) -> None:
        """Test creating an unhealthy integration summary."""
        summary = IntegrationHealthSummary(
            integration="unifi",
            total_entities=100,
            available_entities=20,
            unavailable_entities=80,
            unknown_entities=0,
            health_percentage=20.0,
            domains={"device_tracker": 100},
            sample_unavailable=["device_tracker.phone_1", "device_tracker.phone_2"],
        )
        assert summary.health_percentage == 20.0
        assert len(summary.sample_unavailable) == 2

    def test_integration_to_dict(self) -> None:
        """Test integration summary to dict."""
        summary = IntegrationHealthSummary(
            integration="test",
            total_entities=10,
            available_entities=8,
            unavailable_entities=2,
            unknown_entities=0,
            health_percentage=80.0,
        )
        result = summary.to_dict()

        assert result["integration"] == "test"
        assert result["health_percentage"] == 80.0
        assert result["available_entities"] == 8


class TestAuditResult:
    """Tests for AuditResult."""

    def test_empty_result(self) -> None:
        """Test empty audit result."""
        result = AuditResult(check_name="test")
        assert result.check_name == "test"
        assert len(result.findings) == 0
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.info_count == 0
        assert result.has_findings is False
        assert result.exit_code == 0

    def test_result_with_findings(self) -> None:
        """Test audit result with findings."""
        result = AuditResult(
            check_name="dead-entities",
            findings=[
                AuditFinding(severity=AuditSeverity.ERROR, category="test", message="Error 1"),
                AuditFinding(severity=AuditSeverity.ERROR, category="test", message="Error 2"),
                AuditFinding(severity=AuditSeverity.WARNING, category="test", message="Warning 1"),
                AuditFinding(severity=AuditSeverity.INFO, category="test", message="Info 1"),
            ],
        )
        assert result.error_count == 2
        assert result.warning_count == 1
        assert result.info_count == 1
        assert result.has_findings is True
        assert result.exit_code == 1  # Findings present

    def test_result_with_error(self) -> None:
        """Test audit result with error."""
        result = AuditResult(
            check_name="test",
            error="Connection failed",
        )
        assert result.error == "Connection failed"
        assert result.exit_code == 2  # Error

    def test_result_to_dict(self) -> None:
        """Test audit result to dict."""
        result = AuditResult(
            check_name="test",
            findings=[
                AuditFinding(severity=AuditSeverity.WARNING, category="test", message="Test"),
            ],
            summary={"total_checked": 100},
            execution_time_ms=150.5,
        )
        output = result.to_dict()

        assert output["check_name"] == "test"
        assert len(output["findings"]) == 1
        assert output["summary"]["total_checked"] == 100
        assert output["summary"]["total_findings"] == 1
        assert output["execution_time_ms"] == 150.5
        assert output["exit_code"] == 1
