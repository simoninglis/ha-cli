"""Data models for audit domain."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AuditSeverity(str, Enum):
    """Severity levels for audit findings."""

    ERROR = "error"  # Something is definitely broken
    WARNING = "warning"  # Potential issue worth investigating
    INFO = "info"  # Informational finding


@dataclass
class AuditFinding:
    """Base class for audit findings."""

    severity: AuditSeverity
    category: str
    message: str
    entity_id: str | None = None
    automation_id: str | None = None
    suggested_action: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "severity": self.severity.value,
            "category": self.category,
            "message": self.message,
        }
        if self.entity_id:
            result["entity_id"] = self.entity_id
        if self.automation_id:
            result["automation_id"] = self.automation_id
        if self.suggested_action:
            result["suggested_action"] = self.suggested_action
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class DeadEntityFinding(AuditFinding):
    """Finding for dead/unavailable entities."""

    state: str = ""
    integration: str | None = None
    last_changed: datetime | None = None

    def __post_init__(self) -> None:
        """Initialize base fields."""
        self.category = "dead-entities"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict()
        result["state"] = self.state
        if self.integration:
            result["integration"] = self.integration
        if self.last_changed:
            result["last_changed"] = self.last_changed.isoformat()
        return result


@dataclass
class DuplicateEntityFinding(AuditFinding):
    """Finding for duplicate entities with _2, _3, etc suffixes."""

    base_entity_id: str = ""
    suffix: str = ""
    all_duplicates: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize base fields."""
        self.category = "duplicates"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict()
        result["base_entity_id"] = self.base_entity_id
        result["suffix"] = self.suffix
        result["all_duplicates"] = self.all_duplicates
        return result


@dataclass
class BrokenAutomationFinding(AuditFinding):
    """Finding for automations referencing non-existent or unavailable entities."""

    referenced_entity: str = ""
    entity_exists: bool = False
    entity_available: bool = False
    reference_location: str = ""  # e.g., "trigger", "condition", "action"

    def __post_init__(self) -> None:
        """Initialize base fields."""
        if self.entity_exists:
            self.category = "fragile-automations"
        else:
            self.category = "broken-automations"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict()
        result["referenced_entity"] = self.referenced_entity
        result["entity_exists"] = self.entity_exists
        result["entity_available"] = self.entity_available
        result["reference_location"] = self.reference_location
        return result


@dataclass
class UnusedAutomationFinding(AuditFinding):
    """Finding for automations that haven't triggered recently."""

    last_triggered: datetime | None = None
    days_since_trigger: int | None = None
    automation_name: str = ""
    is_enabled: bool = True

    def __post_init__(self) -> None:
        """Initialize base fields."""
        self.category = "unused-automations"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict()
        if self.last_triggered:
            result["last_triggered"] = self.last_triggered.isoformat()
        result["days_since_trigger"] = self.days_since_trigger
        result["automation_name"] = self.automation_name
        result["is_enabled"] = self.is_enabled
        return result


@dataclass
class TriggerStatsFinding(AuditFinding):
    """Finding for automation trigger statistics."""

    automation_name: str = ""
    trigger_count: int = 0
    last_triggered: datetime | None = None
    is_enabled: bool = True
    triggers: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialize base fields."""
        self.category = "trigger-stats"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict()
        result["automation_name"] = self.automation_name
        result["trigger_count"] = self.trigger_count
        if self.last_triggered:
            result["last_triggered"] = self.last_triggered.isoformat()
        result["is_enabled"] = self.is_enabled
        result["triggers"] = self.triggers
        return result


@dataclass
class IntegrationHealthSummary:
    """Health summary for a single integration."""

    integration: str
    total_entities: int
    available_entities: int
    unavailable_entities: int
    unknown_entities: int
    health_percentage: float
    domains: dict[str, int] = field(default_factory=dict)
    sample_unavailable: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "integration": self.integration,
            "total_entities": self.total_entities,
            "available_entities": self.available_entities,
            "unavailable_entities": self.unavailable_entities,
            "unknown_entities": self.unknown_entities,
            "health_percentage": round(self.health_percentage, 1),
            "domains": self.domains,
            "sample_unavailable": self.sample_unavailable[:5],  # Limit to 5 samples
        }


@dataclass
class AuditResult:
    """Result of an audit operation."""

    check_name: str
    findings: list[AuditFinding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    execution_time_ms: float = 0.0
    error: str | None = None

    @property
    def error_count(self) -> int:
        """Count of error-severity findings."""
        return len([f for f in self.findings if f.severity == AuditSeverity.ERROR])

    @property
    def warning_count(self) -> int:
        """Count of warning-severity findings."""
        return len([f for f in self.findings if f.severity == AuditSeverity.WARNING])

    @property
    def info_count(self) -> int:
        """Count of info-severity findings."""
        return len([f for f in self.findings if f.severity == AuditSeverity.INFO])

    @property
    def has_findings(self) -> bool:
        """Check if there are any findings."""
        return len(self.findings) > 0

    @property
    def exit_code(self) -> int:
        """Get exit code based on findings.

        0 = clean (no findings)
        1 = findings present
        2 = error during audit
        """
        if self.error:
            return 2
        if self.has_findings:
            return 1
        return 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "check_name": self.check_name,
            "findings": [f.to_dict() for f in self.findings],
            "summary": {
                **self.summary,
                "total_findings": len(self.findings),
                "error_count": self.error_count,
                "warning_count": self.warning_count,
                "info_count": self.info_count,
            },
            "execution_time_ms": round(self.execution_time_ms, 2),
            "error": self.error,
            "exit_code": self.exit_code,
        }
