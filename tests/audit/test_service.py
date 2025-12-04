"""Tests for AuditService."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ha_cli.domains.audit.models import (
    AuditResult,
    AuditSeverity,
    BrokenAutomationFinding,
    DeadEntityFinding,
)
from ha_cli.domains.audit.service import AuditService
from ha_cli.domains.entities.models import Entity


@pytest.fixture
def mock_client():
    """Create a mock HA client."""
    client = AsyncMock()
    client.url = "http://localhost:8123"
    client.token = "test-token"
    return client


@pytest.fixture
def sample_entities():
    """Create sample entities for testing."""
    now = datetime.now(timezone.utc)
    return [
        Entity(
            entity_id="light.living_room",
            state="on",
            friendly_name="Living Room Light",
            domain="light",
            attributes={"integration": "hue"},
            last_changed=now,
        ),
        Entity(
            entity_id="light.bedroom",
            state="unavailable",
            friendly_name="Bedroom Light",
            domain="light",
            attributes={"integration": "hue"},
            last_changed=now - timedelta(days=1),
        ),
        Entity(
            entity_id="sensor.temperature",
            state="22.5",
            friendly_name="Temperature",
            domain="sensor",
            attributes={"integration": "esphome"},
            last_changed=now,
        ),
        Entity(
            entity_id="sensor.humidity",
            state="unknown",
            friendly_name="Humidity",
            domain="sensor",
            attributes={"integration": "esphome"},
            last_changed=now,
        ),
        Entity(
            entity_id="light.kitchen_2",
            state="off",
            friendly_name="Kitchen Light 2",
            domain="light",
            attributes={"integration": "hue"},
            last_changed=now,
        ),
        Entity(
            entity_id="light.kitchen",
            state="off",
            friendly_name="Kitchen Light",
            domain="light",
            attributes={"integration": "hue"},
            last_changed=now,
        ),
    ]


@pytest.fixture
def sample_automations():
    """Create sample automations for testing."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=100)

    # Create automation-like objects with required attributes
    class MockAutomation:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    return [
        MockAutomation(
            id="motion_light",
            alias="Motion Light",
            trigger=[{"platform": "state", "entity_id": "binary_sensor.motion"}],
            condition=[],
            action=[{"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}],
            last_triggered=now - timedelta(hours=1),
            enabled=True,
        ),
        MockAutomation(
            id="climate_control",
            alias="Climate Control",
            trigger=[{"platform": "state", "entity_id": "sensor.temperature"}],
            condition=[],
            action=[{"service": "climate.set_temperature", "target": {"entity_id": "climate.bedroom"}}],
            last_triggered=old_date,
            enabled=True,
        ),
        MockAutomation(
            id="never_triggered",
            alias="Never Triggered",
            trigger=[{"platform": "state", "entity_id": "sensor.fake"}],
            condition=[],
            action=[],
            last_triggered=None,
            enabled=True,
        ),
        MockAutomation(
            id="broken_automation",
            alias="Broken Automation",
            trigger=[{"platform": "state", "entity_id": "sensor.deleted"}],
            condition=[],
            action=[{"service": "light.turn_on", "target": {"entity_id": "light.deleted"}}],
            last_triggered=now,
            enabled=True,
        ),
    ]


class TestAuditServiceDeadEntities:
    """Tests for check_dead_entities."""

    @pytest.mark.asyncio
    async def test_finds_unavailable_entities(self, mock_client, sample_entities):
        """Test finding unavailable entities."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()

        result = await service.check_dead_entities()

        assert result.check_name == "dead-entities"
        assert len(result.findings) == 2  # unavailable + unknown

        # Check for the unavailable entity
        unavailable_findings = [f for f in result.findings if f.state == "unavailable"]
        assert len(unavailable_findings) == 1
        assert unavailable_findings[0].entity_id == "light.bedroom"
        assert unavailable_findings[0].severity == AuditSeverity.ERROR

        # Check for the unknown entity
        unknown_findings = [f for f in result.findings if f.state == "unknown"]
        assert len(unknown_findings) == 1
        assert unknown_findings[0].entity_id == "sensor.humidity"
        assert unknown_findings[0].severity == AuditSeverity.WARNING

    @pytest.mark.asyncio
    async def test_filters_by_domain(self, mock_client, sample_entities):
        """Test filtering by domain."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()

        result = await service.check_dead_entities(domain="light")

        # Should only find the light.bedroom which is unavailable
        light_findings = [f for f in result.findings if "light." in f.entity_id]
        assert len(light_findings) <= 1

    @pytest.mark.asyncio
    async def test_filters_by_integration(self, mock_client, sample_entities):
        """Test filtering by integration."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()

        result = await service.check_dead_entities(integration="esphome")

        # Should only find esphome entities
        for finding in result.findings:
            assert finding.integration == "esphome"

    @pytest.mark.asyncio
    async def test_respects_ignore_patterns(self, mock_client, sample_entities):
        """Test that ignore patterns are respected."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()

        result = await service.check_dead_entities(ignore_patterns=["^sensor\\."])

        # Should not find sensor.humidity
        sensor_findings = [f for f in result.findings if "sensor." in f.entity_id]
        assert len(sensor_findings) == 0


class TestAuditServiceDuplicates:
    """Tests for check_duplicates."""

    @pytest.mark.asyncio
    async def test_finds_duplicate_entities(self, mock_client, sample_entities):
        """Test finding duplicate entities with _2 suffix."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()

        result = await service.check_duplicates()

        assert result.check_name == "duplicates"
        # Should find light.kitchen_2 as a duplicate of light.kitchen
        duplicate_findings = [f for f in result.findings if "kitchen" in f.entity_id]
        assert len(duplicate_findings) >= 1

    @pytest.mark.asyncio
    async def test_respects_ignore_patterns(self, mock_client, sample_entities):
        """Test that ignore patterns are respected for duplicates."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()

        result = await service.check_duplicates(ignore_patterns=["kitchen"])

        # Should not find kitchen duplicates
        kitchen_findings = [f for f in result.findings if "kitchen" in f.entity_id]
        assert len(kitchen_findings) == 0


class TestAuditServiceBrokenAutomations:
    """Tests for check_broken_automations."""

    @pytest.mark.asyncio
    async def test_finds_broken_automations(self, mock_client, sample_entities, sample_automations):
        """Test finding automations with non-existent entity references."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()
            service._automation_service.list_all = AsyncMock(return_value=sample_automations)

        result = await service.check_broken_automations()

        assert result.check_name == "broken-automations"
        # Should find references to deleted entities
        broken_findings = [f for f in result.findings if "deleted" in f.referenced_entity]
        assert len(broken_findings) >= 1


class TestAuditServiceFragileAutomations:
    """Tests for check_fragile_automations."""

    @pytest.mark.asyncio
    async def test_finds_fragile_automations(self, mock_client, sample_entities, sample_automations):
        """Test finding automations with unavailable entity references."""
        # Add an automation that references the unavailable bedroom light
        class MockAutomation:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        automations_with_fragile = sample_automations + [
            MockAutomation(
                id="fragile_auto",
                alias="Fragile Automation",
                trigger=[],
                condition=[],
                action=[{"service": "light.turn_on", "target": {"entity_id": "light.bedroom"}}],
                last_triggered=datetime.now(timezone.utc),
                enabled=True,
            )
        ]

        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()
            service._automation_service.list_all = AsyncMock(return_value=automations_with_fragile)

        result = await service.check_fragile_automations()

        assert result.check_name == "fragile-automations"
        # Should find reference to unavailable light.bedroom
        fragile_findings = [f for f in result.findings if f.referenced_entity == "light.bedroom"]
        assert len(fragile_findings) >= 1


class TestAuditServiceUnusedAutomations:
    """Tests for check_unused_automations."""

    @pytest.mark.asyncio
    async def test_finds_never_triggered_automations(self, mock_client, sample_automations):
        """Test finding automations that have never been triggered."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._automation_service = AsyncMock()
            service._automation_service.list_all = AsyncMock(return_value=sample_automations)

        result = await service.check_unused_automations()

        assert result.check_name == "unused-automations"
        never_triggered = [f for f in result.findings if f.days_since_trigger is None]
        assert len(never_triggered) >= 1

    @pytest.mark.asyncio
    async def test_finds_old_triggered_automations(self, mock_client, sample_automations):
        """Test finding automations not triggered in threshold days."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._automation_service = AsyncMock()
            service._automation_service.list_all = AsyncMock(return_value=sample_automations)

        result = await service.check_unused_automations(days=30)

        assert result.check_name == "unused-automations"
        # climate_control was triggered 100 days ago
        old_triggered = [f for f in result.findings if f.days_since_trigger is not None and f.days_since_trigger >= 30]
        assert len(old_triggered) >= 1


class TestAuditServiceTriggerStats:
    """Tests for check_trigger_stats."""

    @pytest.mark.asyncio
    async def test_returns_trigger_statistics(self, mock_client, sample_automations):
        """Test getting trigger statistics."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._automation_service = AsyncMock()
            service._automation_service.list_all = AsyncMock(return_value=sample_automations)

        result = await service.check_trigger_stats()

        assert result.check_name == "trigger-stats"
        assert len(result.findings) > 0


class TestAuditServiceIntegrations:
    """Tests for check_integrations."""

    @pytest.mark.asyncio
    async def test_returns_integration_health(self, mock_client, sample_entities):
        """Test getting integration health summary."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()

        result = await service.check_integrations()

        assert result.check_name == "integrations"
        assert "integrations" in result.summary

    @pytest.mark.asyncio
    async def test_identifies_unhealthy_integrations(self, mock_client):
        """Test identifying integrations with poor health."""
        now = datetime.now(timezone.utc)
        # Create entities with 80% unavailable for unifi integration
        entities = [
            Entity(
                entity_id=f"device_tracker.phone_{i}",
                state="unavailable" if i < 8 else "home",
                friendly_name=f"Phone {i}",
                domain="device_tracker",
                attributes={"integration": "unifi"},
                last_changed=now,
            )
            for i in range(10)
        ]

        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=entities)
            service._automation_service = AsyncMock()

        result = await service.check_integrations()

        # Should have findings for unhealthy unifi integration
        assert len(result.findings) >= 1
        unifi_findings = [f for f in result.findings if "unifi" in f.message]
        assert len(unifi_findings) >= 1


class TestAuditServiceRunAllChecks:
    """Tests for run_all_checks."""

    @pytest.mark.asyncio
    async def test_runs_all_checks(self, mock_client, sample_entities, sample_automations):
        """Test running all audit checks."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()
            service._automation_service.list_all = AsyncMock(return_value=sample_automations)

        result = await service.run_all_checks()

        assert result.check_name == "all"
        assert "checks_run" in result.summary
        assert len(result.summary["checks_run"]) >= 6  # All check types

    @pytest.mark.asyncio
    async def test_severity_filter(self, mock_client, sample_entities, sample_automations):
        """Test filtering by severity."""
        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client
            service._entity_service = AsyncMock()
            service._entity_service.list_entities = AsyncMock(return_value=sample_entities)
            service._automation_service = AsyncMock()
            service._automation_service.list_all = AsyncMock(return_value=sample_automations)

        result = await service.run_all_checks(severity_filter=AuditSeverity.ERROR)

        # All findings should be ERROR or higher
        for finding in result.findings:
            assert finding.severity == AuditSeverity.ERROR


class TestExtractEntityReferences:
    """Tests for entity reference extraction."""

    def test_extracts_trigger_references(self, mock_client):
        """Test extracting entity references from triggers."""
        class MockAutomation:
            def __init__(self):
                self.trigger = [{"platform": "state", "entity_id": "sensor.motion"}]
                self.condition = []
                self.action = []

        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client

        refs = service._extract_entity_references(MockAutomation())

        assert ("sensor.motion", "trigger") in refs

    def test_extracts_action_references(self, mock_client):
        """Test extracting entity references from actions."""
        class MockAutomation:
            def __init__(self):
                self.trigger = []
                self.condition = []
                self.action = [
                    {"service": "light.turn_on", "target": {"entity_id": "light.living_room"}}
                ]

        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client

        refs = service._extract_entity_references(MockAutomation())

        assert ("light.living_room", "action") in refs

    def test_extracts_multiple_entity_ids(self, mock_client):
        """Test extracting multiple entity_ids from a list."""
        class MockAutomation:
            def __init__(self):
                self.trigger = []
                self.condition = []
                self.action = [
                    {"service": "light.turn_on", "target": {"entity_id": ["light.one", "light.two"]}}
                ]

        with patch.object(AuditService, "__init__", lambda x, y: None):
            service = AuditService.__new__(AuditService)
            service.client = mock_client

        refs = service._extract_entity_references(MockAutomation())

        assert ("light.one", "action") in refs
        assert ("light.two", "action") in refs
